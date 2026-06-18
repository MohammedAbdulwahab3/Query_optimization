package main

import (
	"context"
	"fmt"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
)

// CHStore wraps a ClickHouse connection. ALL queries use ? placeholders —
// values are bound as parameters, never string-concatenated.
type CHStore struct {
	conn driver.Conn
	db   string
}

func newCHStore(cfg Config) (*CHStore, error) {
	conn, err := clickhouse.Open(&clickhouse.Options{
		Addr: []string{fmt.Sprintf("%s:%d", cfg.CHHost, cfg.CHPort)},
		Auth: clickhouse.Auth{
			Database: cfg.CHDatabase,
			Username: cfg.CHUser,
			Password: cfg.CHPassword,
		},
		DialTimeout: 10 * time.Second,
	})
	if err != nil {
		return nil, err
	}
	return &CHStore{conn: conn, db: cfg.CHDatabase}, nil
}

func (s *CHStore) ping(ctx context.Context) error { return s.conn.Ping(ctx) }

// --- result types ---

type Profile struct {
	Number           string  `json:"number"`
	SubscriberName   string  `json:"subscriber_name"`
	Operator         string  `json:"operator"`
	DeviceModel      string  `json:"device_model"`
	IMEI             string  `json:"imei"`
	IMSI             string  `json:"imsi"`
	RegistrationDate string  `json:"registration_date"`
	CallCount        uint64  `json:"call_count"`
	TotalMinutes     float64 `json:"total_minutes"`
}

type MapPoint struct {
	Latitude     float64 `json:"latitude"`
	Longitude    float64 `json:"longitude"`
	LocationName string  `json:"location_name"`
	Hits         uint64  `json:"hits"`
}

type CallRecord struct {
	RecordID     string    `json:"record_id"`
	Caller       string    `json:"caller_number"`
	Callee       string    `json:"callee_number"`
	CallType     string    `json:"call_type"`
	Direction    string    `json:"direction"`
	CallStart    time.Time `json:"call_start"`
	CallEnd      time.Time `json:"call_end"`
	DurationSec  uint32    `json:"duration_sec"`
	CallResult   string    `json:"call_result"`
	LocationName string    `json:"location_name"`
	Latitude     float64   `json:"latitude"`
	Longitude    float64   `json:"longitude"`
	NetworkType  string    `json:"network_type"`
	ChargeAmount float64   `json:"charge_amount"`
}

// Profile: latest A-party record gives the identity fields; the daily rollup
// gives fast aggregate counts/minutes (counting the number as A- or B-party).
func (s *CHStore) Profile(ctx context.Context, number string) (*Profile, error) {
	p := &Profile{Number: number}

	var regDate time.Time
	row := s.conn.QueryRow(ctx, fmt.Sprintf(`
		SELECT subscriber_name, operator, device_model, imei, imsi, registration_date
		FROM %s.cdr
		WHERE caller_number = ?
		ORDER BY call_start DESC
		LIMIT 1`, s.db), number)
	if err := row.Scan(&p.SubscriberName, &p.Operator, &p.DeviceModel,
		&p.IMEI, &p.IMSI, &regDate); err != nil {
		return nil, err // not found -> caller maps to 404
	}
	p.RegistrationDate = regDate.Format("2006-01-02")

	var totalSec uint64
	row = s.conn.QueryRow(ctx, fmt.Sprintf(`
		SELECT sum(call_count), sum(total_duration_sec)
		FROM %s.cdr_daily_rollup
		WHERE number = ?`, s.db), number)
	if err := row.Scan(&p.CallCount, &totalSec); err != nil {
		return nil, err
	}
	p.TotalMinutes = float64(totalSec) / 60.0
	return p, nil
}

// MapPoints: pre-aggregated tower hits from the location rollup.
func (s *CHStore) MapPoints(ctx context.Context, number string, limit int) ([]MapPoint, error) {
	rows, err := s.conn.Query(ctx, fmt.Sprintf(`
		SELECT latitude, longitude, location_name, sum(hits) AS hits
		FROM %s.cdr_location_rollup
		WHERE number = ?
		GROUP BY latitude, longitude, location_name
		ORDER BY hits DESC
		LIMIT ?`, s.db), number, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	points := []MapPoint{}
	for rows.Next() {
		var p MapPoint
		if err := rows.Scan(&p.Latitude, &p.Longitude, &p.LocationName, &p.Hits); err != nil {
			return nil, err
		}
		points = append(points, p)
	}
	return points, rows.Err()
}

// Timeline: paginated call records for a number (as A- or B-party), with an
// optional [from, to) date-range filter. The OR uses both the primary key
// (caller_number) and the callee projection.
func (s *CHStore) Timeline(ctx context.Context, number string, from, to time.Time,
	limit, offset int) ([]CallRecord, uint64, error) {

	var total uint64
	row := s.conn.QueryRow(ctx, fmt.Sprintf(`
		SELECT count()
		FROM %s.cdr
		WHERE (caller_number = ? OR callee_number = ?)
		  AND call_start >= ? AND call_start < ?`, s.db),
		number, number, from, to)
	if err := row.Scan(&total); err != nil {
		return nil, 0, err
	}

	rows, err := s.conn.Query(ctx, fmt.Sprintf(`
		SELECT record_id, caller_number, callee_number, call_type, direction,
		       call_start, call_end, duration_sec, call_result, location_name,
		       latitude, longitude, network_type, toFloat64(charge_amount)
		FROM %s.cdr
		WHERE (caller_number = ? OR callee_number = ?)
		  AND call_start >= ? AND call_start < ?
		ORDER BY call_start DESC
		LIMIT ? OFFSET ?`, s.db),
		number, number, from, to, limit, offset)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	records := []CallRecord{}
	for rows.Next() {
		var r CallRecord
		if err := rows.Scan(&r.RecordID, &r.Caller, &r.Callee, &r.CallType,
			&r.Direction, &r.CallStart, &r.CallEnd, &r.DurationSec, &r.CallResult,
			&r.LocationName, &r.Latitude, &r.Longitude, &r.NetworkType,
			&r.ChargeAmount); err != nil {
			return nil, 0, err
		}
		records = append(records, r)
	}
	return records, total, rows.Err()
}

type CoLocatedEvent struct {
	Number    string `json:"number"`
	Events    uint64 `json:"events"`
	FirstSeen string `json:"first_seen"`
	LastSeen  string `json:"last_seen"`
}

// --- auth: warrants + audit log ---

// ActiveWarrant returns the id of an active warrant covering number, or "".
func (s *CHStore) ActiveWarrant(ctx context.Context, number string) (string, error) {
	var id string
	row := s.conn.QueryRow(ctx, fmt.Sprintf(`
		SELECT warrant_id FROM %s.warrants
		WHERE target_number = ? AND valid_from <= now() AND valid_to >= now()
		ORDER BY valid_to DESC LIMIT 1`, s.db), number)
	if err := row.Scan(&id); err != nil {
		return "", nil // no row -> no active warrant (not an error)
	}
	return id, nil
}

// WriteAudit appends an access record (best-effort; never blocks the request).
func (s *CHStore) WriteAudit(ctx context.Context, analyst, action, target, warrantID, result, ip string) {
	_ = s.conn.Exec(ctx, fmt.Sprintf(`
		INSERT INTO %s.audit_log (analyst, action, target, warrant_id, result, client_ip)
		VALUES (?, ?, ?, ?, ?, ?)`, s.db),
		analyst, action, target, warrantID, result, ip)
}

type AuditEntry struct {
	Ts        string `json:"ts"`
	Analyst   string `json:"analyst"`
	Action    string `json:"action"`
	Target    string `json:"target"`
	WarrantID string `json:"warrant_id"`
	Result    string `json:"result"`
	ClientIP  string `json:"client_ip"`
}

// RecentAudit returns the latest audit entries (for the audit view).
func (s *CHStore) RecentAudit(ctx context.Context, limit int) ([]AuditEntry, error) {
	rows, err := s.conn.Query(ctx, fmt.Sprintf(`
		SELECT toString(ts), analyst, action, target, warrant_id, result, client_ip
		FROM %s.audit_log ORDER BY ts DESC LIMIT ?`, s.db), limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []AuditEntry{}
	for rows.Next() {
		var e AuditEntry
		if err := rows.Scan(&e.Ts, &e.Analyst, &e.Action, &e.Target, &e.WarrantID,
			&e.Result, &e.ClientIP); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

// --- pattern-of-life + trajectory ---

type HeatCell struct {
	Dow   uint8  `json:"dow"` // 1=Mon … 7=Sun
	Hour  uint8  `json:"hour"`
	Calls uint64 `json:"calls"`
}

type TowerRef struct {
	LocationName string  `json:"location_name"`
	CellID       string  `json:"cell_id"`
	Latitude     float64 `json:"latitude"`
	Longitude    float64 `json:"longitude"`
	Count        uint64  `json:"count"`
}

type PatternsResult struct {
	Number  string     `json:"number"`
	Heatmap []HeatCell `json:"heatmap"`
	Home    *TowerRef  `json:"home"`
	Work    *TowerRef  `json:"work"`
}

// Patterns returns a day-of-week × hour call heatmap plus inferred home tower
// (most-used at night, 20:00–06:00) and work tower (most-used weekday daytime).
func (s *CHStore) Patterns(ctx context.Context, number string) (*PatternsResult, error) {
	res := &PatternsResult{Number: number, Heatmap: []HeatCell{}}

	rows, err := s.conn.Query(ctx, fmt.Sprintf(`
		WITH ev AS (
			SELECT call_start FROM %s.cdr
			WHERE caller_number = ? OR callee_number = ?
		)
		SELECT toDayOfWeek(call_start) AS dow, toHour(call_start) AS hour, count() AS calls
		FROM ev GROUP BY dow, hour ORDER BY dow, hour`, s.db), number, number)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var h HeatCell
		if err := rows.Scan(&h.Dow, &h.Hour, &h.Calls); err != nil {
			rows.Close()
			return nil, err
		}
		res.Heatmap = append(res.Heatmap, h)
	}
	rows.Close()

	res.Home = s.topTower(ctx, number,
		"(toHour(call_start) >= 20 OR toHour(call_start) < 6)")
	res.Work = s.topTower(ctx, number,
		"toHour(call_start) BETWEEN 9 AND 17 AND toDayOfWeek(call_start) <= 5")
	return res, nil
}

// topTower returns the most-used tower for a number under a time predicate, or
// nil if there are no matching connections.
func (s *CHStore) topTower(ctx context.Context, number, timePred string) *TowerRef {
	t := &TowerRef{}
	row := s.conn.QueryRow(ctx, fmt.Sprintf(`
		SELECT location_name, cell_id, latitude, longitude, count() AS c
		FROM %s.cdr
		WHERE (caller_number = ? OR callee_number = ?) AND %s
		GROUP BY location_name, cell_id, latitude, longitude
		ORDER BY c DESC LIMIT 1`, s.db, timePred), number, number)
	if err := row.Scan(&t.LocationName, &t.CellID, &t.Latitude, &t.Longitude, &t.Count); err != nil {
		return nil
	}
	return t
}

type TrajPoint struct {
	Time         string  `json:"time"`
	Latitude     float64 `json:"latitude"`
	Longitude    float64 `json:"longitude"`
	LocationName string  `json:"location_name"`
	CellID       string  `json:"cell_id"`
}

type TrajectoryResult struct {
	Number string      `json:"number"`
	Points []TrajPoint `json:"points"`
}

// Trajectory returns a number's tower connections in chronological order for
// movement playback on the map.
func (s *CHStore) Trajectory(ctx context.Context, number string, from, to time.Time,
	limit int) (*TrajectoryResult, error) {

	res := &TrajectoryResult{Number: number, Points: []TrajPoint{}}
	rows, err := s.conn.Query(ctx, fmt.Sprintf(`
		SELECT toString(call_start), latitude, longitude, location_name, cell_id
		FROM %s.cdr
		WHERE (caller_number = ? OR callee_number = ?)
		  AND call_start >= ? AND call_start < ?
		ORDER BY call_start ASC
		LIMIT ?`, s.db), number, number, from, to, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var p TrajPoint
		if err := rows.Scan(&p.Time, &p.Latitude, &p.Longitude, &p.LocationName, &p.CellID); err != nil {
			return nil, err
		}
		res.Points = append(res.Points, p)
	}
	return res, rows.Err()
}

// --- suspicious-pattern detection ---

type Flag struct {
	Code     string `json:"code"`
	Label    string `json:"label"`
	Severity string `json:"severity"` // low | medium | high
	Detail   string `json:"detail"`
}

type FlagsResult struct {
	Number     string   `json:"number"`
	TotalCalls uint64   `json:"total_calls"`
	Contacts   uint64   `json:"contacts"`
	ActiveDays uint64   `json:"active_days"`
	OutRatio   float64  `json:"out_ratio"`
	NightRatio float64  `json:"night_ratio"`
	FirstSeen  string   `json:"first_seen"`
	LastSeen   string   `json:"last_seen"`
	SharedIMEI []string `json:"shared_imei_numbers"`
	Flags      []Flag   `json:"flags"`
}

// Flags computes behavioral metrics for a number and derives suspicious-pattern
// flags (shared device / SIM-swap, possible burner, high night activity,
// mostly-outgoing). Activity counts the number as A- or B-party.
func (s *CHStore) Flags(ctx context.Context, number string) (*FlagsResult, error) {
	res := &FlagsResult{Number: number, SharedIMEI: []string{}, Flags: []Flag{}}

	row := s.conn.QueryRow(ctx, fmt.Sprintf(`
		WITH ev AS (
			SELECT call_start, (caller_number = ?) AS is_out,
			       if(caller_number = ?, callee_number, caller_number) AS other
			FROM %s.cdr WHERE caller_number = ? OR callee_number = ?
		)
		SELECT count() AS total, uniq(other) AS contacts,
		       uniq(toDate(call_start)) AS active_days,
		       if(count() = 0, 0, countIf(is_out) / count()) AS out_ratio,
		       if(count() = 0, 0, countIf(toHour(call_start) < 5) / count()) AS night_ratio,
		       toString(min(call_start)) AS first_seen,
		       toString(max(call_start)) AS last_seen
		FROM ev`, s.db),
		number, number, number, number)
	if err := row.Scan(&res.TotalCalls, &res.Contacts, &res.ActiveDays,
		&res.OutRatio, &res.NightRatio, &res.FirstSeen, &res.LastSeen); err != nil {
		return nil, err
	}

	if err := s.conn.QueryRow(ctx, fmt.Sprintf(`
		SELECT groupUniqArray(caller_number)
		FROM %s.cdr
		WHERE imei = (SELECT any(imei) FROM %s.cdr WHERE caller_number = ?)
		  AND caller_number != ?`, s.db, s.db),
		number, number).Scan(&res.SharedIMEI); err != nil {
		return nil, err
	}

	// derive flags
	if len(res.SharedIMEI) > 0 {
		res.Flags = append(res.Flags, Flag{
			Code: "shared_device", Label: "Shared device (possible SIM-swap)",
			Severity: "high",
			Detail:   fmt.Sprintf("IMEI also used by %d other number(s)", len(res.SharedIMEI)),
		})
	}
	if res.Contacts <= 3 && res.ActiveDays <= 10 && res.TotalCalls > 0 && res.TotalCalls <= 30 {
		res.Flags = append(res.Flags, Flag{
			Code: "burner", Label: "Possible burner phone", Severity: "high",
			Detail: fmt.Sprintf("%d calls, %d contacts, active %d day(s)",
				res.TotalCalls, res.Contacts, res.ActiveDays),
		})
	}
	if res.NightRatio >= 0.4 && res.TotalCalls >= 10 {
		res.Flags = append(res.Flags, Flag{
			Code: "night_activity", Label: "High late-night activity", Severity: "medium",
			Detail: fmt.Sprintf("%.0f%% of calls between 00:00–05:00", res.NightRatio*100),
		})
	}
	if res.OutRatio >= 0.85 && res.TotalCalls >= 10 {
		res.Flags = append(res.Flags, Flag{
			Code: "mostly_outgoing", Label: "Almost exclusively outgoing", Severity: "low",
			Detail: fmt.Sprintf("%.0f%% outgoing", res.OutRatio*100),
		})
	}
	return res, nil
}

type SimSwapGroup struct {
	IMEI    string   `json:"imei"`
	Count   uint64   `json:"count"`
	Numbers []string `json:"numbers"`
}

type BurnerAlert struct {
	Number     string `json:"number"`
	Calls      uint64 `json:"calls"`
	Contacts   uint64 `json:"contacts"`
	ActiveDays uint64 `json:"active_days"`
}

type NightOwlAlert struct {
	Number     string  `json:"number"`
	Calls      uint64  `json:"calls"`
	NightRatio float64 `json:"night_ratio"`
}

type AlertsResult struct {
	SimSwap   []SimSwapGroup  `json:"sim_swap"`
	Burners   []BurnerAlert   `json:"burners"`
	NightOwls []NightOwlAlert `json:"night_owls"`
}

// Alerts runs dataset-wide suspicious-pattern detection.
func (s *CHStore) Alerts(ctx context.Context, limit int) (*AlertsResult, error) {
	res := &AlertsResult{SimSwap: []SimSwapGroup{}, Burners: []BurnerAlert{}, NightOwls: []NightOwlAlert{}}

	rows, err := s.conn.Query(ctx, fmt.Sprintf(`
		SELECT imei, length(groupUniqArray(caller_number)) AS cnt,
		       groupUniqArray(caller_number) AS nums
		FROM %s.cdr GROUP BY imei HAVING cnt > 1 ORDER BY cnt DESC LIMIT ?`, s.db), limit)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var g SimSwapGroup
		if err := rows.Scan(&g.IMEI, &g.Count, &g.Numbers); err != nil {
			rows.Close()
			return nil, err
		}
		res.SimSwap = append(res.SimSwap, g)
	}
	rows.Close()

	rows, err = s.conn.Query(ctx, fmt.Sprintf(`
		WITH ev AS (
			SELECT caller_number AS n, call_start, callee_number AS other FROM %s.cdr
			UNION ALL
			SELECT callee_number AS n, call_start, caller_number AS other FROM %s.cdr)
		SELECT n AS number, count() AS calls, uniq(other) AS contacts,
		       uniq(toDate(call_start)) AS active_days
		FROM ev GROUP BY n
		HAVING contacts <= 3 AND active_days <= 10 AND calls <= 30
		ORDER BY calls DESC LIMIT ?`, s.db, s.db), limit)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var b BurnerAlert
		if err := rows.Scan(&b.Number, &b.Calls, &b.Contacts, &b.ActiveDays); err != nil {
			rows.Close()
			return nil, err
		}
		res.Burners = append(res.Burners, b)
	}
	rows.Close()

	rows, err = s.conn.Query(ctx, fmt.Sprintf(`
		WITH ev AS (
			SELECT caller_number AS n, call_start FROM %s.cdr
			UNION ALL
			SELECT callee_number AS n, call_start FROM %s.cdr)
		SELECT n AS number, count() AS calls,
		       countIf(toHour(call_start) < 5) / count() AS night_ratio
		FROM ev GROUP BY n
		HAVING calls >= 10 AND night_ratio >= 0.4
		ORDER BY night_ratio DESC LIMIT ?`, s.db, s.db), limit)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var o NightOwlAlert
		if err := rows.Scan(&o.Number, &o.Calls, &o.NightRatio); err != nil {
			rows.Close()
			return nil, err
		}
		res.NightOwls = append(res.NightOwls, o)
	}
	rows.Close()

	return res, nil
}

// CoLocationInTime: other subscribers connected at the SAME cell tower within
// windowSec of one of the target's connections — a space+time proximity signal
// (much stronger than "shared a tower ever"). Temporal self-join on cell_id.
func (s *CHStore) CoLocationInTime(ctx context.Context, number string,
	windowSec, limit int) ([]CoLocatedEvent, error) {

	rows, err := s.conn.Query(ctx, fmt.Sprintf(`
		WITH tgt AS (
			SELECT cell_id, call_start
			FROM %s.cdr
			WHERE caller_number = ? OR callee_number = ?
		)
		SELECT o.caller_number AS number, count() AS events,
		       toString(min(o.call_start)) AS first_seen,
		       toString(max(o.call_start)) AS last_seen
		FROM %s.cdr AS o
		INNER JOIN tgt ON o.cell_id = tgt.cell_id
		WHERE o.caller_number != ?
		  AND abs(dateDiff('second', o.call_start, tgt.call_start)) <= ?
		GROUP BY number
		ORDER BY events DESC
		LIMIT ?`, s.db, s.db),
		number, number, number, windowSec, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []CoLocatedEvent{}
	for rows.Next() {
		var e CoLocatedEvent
		if err := rows.Scan(&e.Number, &e.Events, &e.FirstSeen, &e.LastSeen); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

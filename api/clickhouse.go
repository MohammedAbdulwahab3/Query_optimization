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

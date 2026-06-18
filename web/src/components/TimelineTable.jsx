import React, { useState } from "react";
import { FixedSizeList as List } from "react-window";
import { useTimeline } from "../api.js";

const ROW_H = 34;
const PAGE_SIZE = 200;

function fmt(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function TimelineTable({ number }) {
  const [page, setPage] = useState(1);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const { data, isLoading, isError, error } = useTimeline(number, {
    page,
    pageSize: PAGE_SIZE,
    from,
    to,
  });

  const records = data?.records || [];
  const total = data?.total || 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const Row = ({ index, style }) => {
    const r = records[index];
    return (
      <div className="trow" style={style}>
        <span className="c-time">{fmt(r.call_start)}</span>
        <span className="c-num">{r.caller_number}</span>
        <span className="c-num">{r.callee_number}</span>
        <span className="c-type">{r.call_type}</span>
        <span className="c-dir">{r.direction}</span>
        <span className="c-dur">{r.duration_sec}s</span>
        <span className={`c-res res-${r.call_result}`}>{r.call_result}</span>
        <span className="c-loc">{r.location_name}</span>
        <span className="c-net">{r.network_type}</span>
      </div>
    );
  };

  return (
    <div className="panel timeline">
      <div className="timeline-head">
        <h3>Timeline ({total.toLocaleString()} records)</h3>
        <div className="filters">
          <label>
            From <input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
          </label>
          <label>
            To <input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} />
          </label>
        </div>
      </div>

      <div className="trow theader">
        <span className="c-time">Start</span>
        <span className="c-num">Caller</span>
        <span className="c-num">Callee</span>
        <span className="c-type">Type</span>
        <span className="c-dir">Dir</span>
        <span className="c-dur">Dur</span>
        <span className="c-res">Result</span>
        <span className="c-loc">Location</span>
        <span className="c-net">Net</span>
      </div>

      {isLoading && <p className="muted">Loading…</p>}
      {isError && <p className="error">{String(error.message)}</p>}
      {!isLoading && !isError && records.length === 0 && (
        <p className="muted">No records in range.</p>
      )}

      {records.length > 0 && (
        <List
          height={Math.min(records.length, 12) * ROW_H}
          itemCount={records.length}
          itemSize={ROW_H}
          width="100%"
        >
          {Row}
        </List>
      )}

      <div className="pager">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹ Prev</button>
        <span>Page {page} / {pages}</span>
        <button disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next ›</button>
      </div>
    </div>
  );
}

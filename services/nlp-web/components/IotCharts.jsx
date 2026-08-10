'use client'

// Raw Response from AWS
// [
//["{type=null, event_source=null, gateway_id=null, device_id=misty_03953, device_name=Misty Robot 1, timestamp=1756311160, sensor_id=cv, event=intruder_detected, person=unknown person, yaw=11, pitch=-9, distance=81}"],
// ["{type=65, event_source=5, gateway_id=2e7ac9639237415e9d242aff8ed2198a, device_id=V8o=-2, device_name=Door Sensor, timestamp=1756311163, sensor_id=null, event=null, person=null, yaw=null, pitch=null, distance=null}"],
// ["{type=65, event_source=5, gateway_id=2e7ac9639237415e9d242aff8ed2198a, device_id=V8o=-2, device_name=Door Sensor, timestamp=1756311158, sensor_id=null, event=null, person=null, yaw=null, pitch=null, distance=null}"],
// ["{type=65, event_source=5, gateway_id=2e7ac9639237415e9d242aff8ed2198a, device_id=V8o=-2, device_name=Door Sensor, timestamp=1756311149, sensor_id=null, event=null, person=null, yaw=null, pitch=null, distance=null}"]
//]

import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, BarChart, Bar, ResponsiveContainer } from "recharts";

function floorToMinute(d) {
  const t = d.getTime();
  return new Date(Math.floor(t / 60000) * 60000);
}
function isoNoTZ(d) { return d.toISOString().slice(0,19).replace("T"," "); }

export default function IoTCharts() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch("/testDataS3.json")
      .then(r => r.json())
      .then(raw => {
        const seen = new Set();
        const v = [];
        for (const r of raw) {
          if (seen.has(r.id)) continue;
          seen.add(r.id);
          const ts = new Date(((r.value && r.value.timestamp) || 0) * 1000);
          v.push({ id: r.id, device: r.deviceName, type: r.value && r.value.type, ts });
        }
        v.sort((a,b) => a.ts - b.ts);
        setRows(v);
      })
      .catch(setErr);
  }, []);

  const { minuteSeries, minuteLabels, devices, totals } = useMemo(() => {
    if (!rows) return { minuteSeries: [], minuteLabels: [], devices: [], totals: [] };
    const labelSet = new Set();
    const devs = [...new Set(rows.map(r => r.device))];
    const map = Object.fromEntries(devs.map(d => [d, new Map()]));
    for (const r of rows) {
      const key = isoNoTZ(floorToMinute(r.ts));
      labelSet.add(key);
      const m = map[r.device];
      m.set(key, (m.get(key) || 0) + 1);
    }
    const labels = [...labelSet].sort();
    const ser = labels.map(lbl => {
      const row = { minute: lbl };
      for (const d of devs) row[d] = map[d].get(lbl) || 0;
      return row;
    });
    const totals = devs.map(d => ({ device: d, count: rows.filter(r => r.device === d).length }));
    return { minuteSeries: ser, minuteLabels: labels, devices: devs, totals };
  }, [rows]);

  if (err) return <div style={{color:"#b91c1c"}}>Failed to load data.</div>;
  if (!rows) return <div>Loading…</div>;

  const first = rows[0]?.ts, last = rows[rows.length-1]?.ts;

  return (
    <div style={{fontFamily:"system-ui, -apple-system, Segoe UI, Roboto, Ubuntu", padding: 16}}>
      <h2 style={{marginBottom:8}}>IoT events per minute (by device)</h2>
      <div style={{display:"flex", gap:16, flexWrap:"wrap"}}>
        <div style={{flex:"2 1 700px", border:"1px solid #e5e7eb", borderRadius:12, padding:16}}>
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={minuteSeries}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="minute" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              {devices.map((d, i) => (
                <Line key={d} dataKey={d} type="monotone" dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div style={{flex:"1 1 320px", border:"1px solid #e5e7eb", borderRadius:12, padding:16}}>
          <h3>Meta</h3>
          <div style={{display:"flex", gap:8, flexWrap:"wrap", fontSize:12}}>
            {first && last && <>
              <span style={badgeStyle}>From: {isoNoTZ(first)}Z</span>
              <span style={badgeStyle}>To: {isoNoTZ(last)}Z</span>
              <span style={badgeStyle}>Freshness: {Math.round((Date.now()-last.getTime())/1000)}s</span>
            </>}
            <span style={badgeStyle}>Total events: {rows.length}</span>
          </div>

          <h3 style={{marginTop:12}}>Totals by device</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={totals}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="device" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

const badgeStyle = {
  display:"inline-block",
  padding:"4px 8px",
  background:"#f3f4f6",
  borderRadius:999
};
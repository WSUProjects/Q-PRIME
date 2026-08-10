// MyChartWithButton.jsx
import { useCallback, useState } from "react"

import {BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer} from "recharts"

// If you have these wrappers in your project, keep them;
// otherwise remove them and render the <ResponsiveContainer> directly.
import { ChartContainer, ChartTooltipContent } from "@/components/ui/charts"

export default function MyChartWithButton() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)

  const loadData = useCallback(async () => {
    try {
      setErr(null)
      setLoading(true)

      // If the file is in /public
      const url = `${import.meta.env.BASE_URL || "/"}testDataS3.json`
      const raw = await fetch(url).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })

      // --- transform: de-dup by id, count per device ---
      const seen = new Set()
      const counts = new Map()
      for (const row of raw) {
        if (seen.has(row.id)) continue
        seen.add(row.id)
        const device = row.deviceName
        counts.set(device, (counts.get(device) || 0) + 1)
      }
      // Recharts shape
      const chartData = [...counts.entries()].map(([name, value]) => ({ name, value }))
      setData(chartData)
    } catch (e) {
      setErr(e)
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div style={{ fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Ubuntu", display:"grid", gap:12 }}>
      <div style={{ display:"flex", gap:8 }}>
        <button
          onClick={loadData}
          disabled={loading}
          style={{
            padding:"8px 12px", border:"1px solid #e5e7eb", borderRadius:8,
            background: loading ? "#f3f4f6" : "white", cursor: loading ? "not-allowed" : "pointer"
          }}
        >
          {data ? (loading ? "Reloading…" : "Reload chart") : (loading ? "Loading…" : "Load chart")}
        </button>
        {err && <span style={{ color:"#b91c1c" }}>Error: {String(err.message || err)}</span>}
      </div>

      {data && (
        <ChartContainer>
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              {/* If you don’t have ChartTooltipContent, swap for <Tooltip /> */}
              <Tooltip content={<ChartTooltipContent />} />
              <Bar dataKey="value" />
            </BarChart>
          </ResponsiveContainer>
        </ChartContainer>
      )}
    </div>
  )
}

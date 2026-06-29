/**
 * 延迟分布图表组件。
 *
 * 本文件负责把 metrics 快照中的延迟桶转换为图表数据并渲染柱状图。它不负责
 * 拉取监控接口或维护 dashboard 状态。
 */
import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { LatencyDistribution } from '@/types';

// ---- 5 fixed buckets per spec §3 ----
const BUCKETS = [
  { key: 'under_100ms', label: '<100ms', fill: '#32D583' },
  { key: '100_500ms', label: '100-500', fill: '#2F7BFF' },
  { key: '500ms_1s', label: '500-1s', fill: '#57A0FF' },
  { key: '1s_5s', label: '1-5s', fill: '#F5B942' },
  { key: 'over_5s', label: '>5s', fill: '#F05D68' },
] as const;

interface LatencyHistogramProps {
  distribution: LatencyDistribution | null;
}

export function LatencyHistogram({ distribution }: LatencyHistogramProps) {
  const data = useMemo(() => {
    if (!distribution) return BUCKETS.map((b) => ({ name: b.label, value: 0 }));
    return BUCKETS.map((b) => ({
      name: b.label,
      value: distribution[b.key as keyof LatencyDistribution] ?? 0,
    }));
  }, [distribution]);

  const total = useMemo(
    () => data.reduce((sum, d) => sum + d.value, 0),
    [data]
  );

  return (
    <div className="border border-crt-border bg-crt-bg-elevated p-4 rounded-lg">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="font-label text-crt-fg-muted tracking-[0.12em]">
          延迟分布
        </span>
        {total > 0 && (
          <span className="font-label text-crt-fg-muted">
            共 {total.toLocaleString()} 次
          </span>
        )}
      </div>

      {/* Chart */}
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 4, right: 4, bottom: 0, left: 4 }}
            barCategoryGap="12%"
          >
            {/* No grid lines — industrial de-noise */}
            <XAxis
              dataKey="name"
              tick={{
                fill: '#91A7C4',
                fontSize: 10,
                fontFamily: 'JetBrains Mono, monospace',
              }}
              axisLine={{ stroke: '#203451' }}
              tickLine={false}
            />
            <YAxis
              tick={{
                fill: '#91A7C4',
                fontSize: 10,
                fontFamily: 'JetBrains Mono, monospace',
              }}
              axisLine={{ stroke: '#203451' }}
              tickLine={false}
              width={50}
            />
            <Tooltip
              cursor={{ fill: 'rgba(255,255,255,0.03)' }}
              contentStyle={{
                background: '#0B1728',
                border: '1px solid #203451',
                borderRadius: 6,
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '11px',
                color: '#EAEAEA',
              }}
              labelStyle={{ color: '#888888', fontSize: '9px', marginBottom: 4 }}
              formatter={(value) => {
                const v = Number(value);
                return total > 0
                  ? [`${v.toLocaleString()} (${((v / total) * 100).toFixed(1)}%)`, '数量']
                  : [v, '数量'];
              }}
            />
            <Bar dataKey="value" radius={0}>
              {data.map((_entry, index) => (
                <Cell key={index} fill={BUCKETS[index].fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Legend row */}
      <div className="flex gap-4 mt-3 flex-wrap">
        {BUCKETS.map((b, i) => (
          <div key={b.key} className="flex items-center gap-1.5">
            <div
              className="w-2 h-2"
              style={{ backgroundColor: b.fill }}
            />
            <span className="font-label text-crt-fg-muted">
              {b.label}
              {total > 0 && data[i].value > 0
                ? ` ${((data[i].value / total) * 100).toFixed(1)}%`
                : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

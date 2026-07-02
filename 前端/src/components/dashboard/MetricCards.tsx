/**
 * 指标卡片组件集合。
 *
 * 本文件负责展示请求量、缓存命中率、token、成本和平均延迟等汇总指标。
 * 它不负责请求监控接口或处理 trace 明细。
 */
import { memo } from 'react';
import type { MetricsSnapshot } from '@/types';

// ---- Individual cards, each React.memo'd ----

interface CardProps {
  value: string;
  label: string;
  sub: string;
  accent?: 'red' | 'green' | 'dim';
}

const MetricCard = memo(function MetricCard({
  value,
  label,
  sub,
  accent,
}: CardProps) {
  const colorClass =
    accent === 'red'
      ? 'text-crt-red'
      : accent === 'green'
      ? 'text-crt-green'
      : 'text-crt-fg';

  return (
    <div className="surface-panel flex min-h-[112px] flex-col justify-between p-4">
      <div className="font-label text-crt-fg-muted tracking-[0.12em]">
        {label}
      </div>
      <div className={`text-[24px] font-semibold leading-none tabular-nums ${colorClass}`}>
        {value}
      </div>
      <div className="font-label text-crt-fg-muted mt-1">
        {sub}
      </div>
    </div>
  );
});

// ---- Memo selectors: each card only re-renders when its slice changes ----

const TotalRequestsCard = memo(function TotalRequestsCard({
  snapshot,
}: {
  snapshot: MetricsSnapshot | null;
}) {
  return (
    <MetricCard
      value={snapshot ? snapshot.total_requests.toLocaleString() : '-'}
      label="请求总数"
      sub="累计请求量"
    />
  );
});
TotalRequestsCard.displayName = 'TotalRequestsCard';

const CacheHitRateCard = memo(function CacheHitRateCard({
  snapshot,
}: {
  snapshot: MetricsSnapshot | null;
}) {
  const rate = snapshot ? (snapshot.cache_hit_rate * 100).toFixed(1) + '%' : '-';
  return (
    <MetricCard
      value={rate}
      label="缓存命中率"
      sub={
        snapshot
          ? `${snapshot.cache_hits.toLocaleString()} 次命中 / ${snapshot.cache_misses.toLocaleString()} 次未命中`
          : '命中 / 未命中'
      }
      accent={snapshot && snapshot.cache_hit_rate >= 0.4 ? 'green' : undefined}
    />
  );
});
CacheHitRateCard.displayName = 'CacheHitRateCard';

const TokenCostCard = memo(function TokenCostCard({
  snapshot,
}: {
  snapshot: MetricsSnapshot | null;
}) {
  const tokens = snapshot ? snapshot.total_tokens.toLocaleString() : '-';
  const cost = snapshot ? '$' + snapshot.total_cost_usd.toFixed(4) : '$-';
  return (
    <MetricCard
      value={tokens}
      label="Token 消耗"
      sub={`预估成本 ${cost}`}
    />
  );
});
TokenCostCard.displayName = 'TokenCostCard';

const AvgLatencyCard = memo(function AvgLatencyCard({
  snapshot,
}: {
  snapshot: MetricsSnapshot | null;
}) {
  const latency = snapshot
    ? Math.round(snapshot.avg_latency_ms) + 'ms'
    : '-';
  return (
    <MetricCard
      value={latency}
      label="平均延迟"
      sub="端到端耗时"
      accent={
        snapshot
          ? snapshot.avg_latency_ms > 1000
            ? 'red'
            : snapshot.avg_latency_ms < 200
            ? 'green'
            : undefined
          : undefined
      }
    />
  );
});
AvgLatencyCard.displayName = 'AvgLatencyCard';

// ---- Composite grid ----

interface MetricCardsProps {
  snapshot: MetricsSnapshot | null;
}

export function MetricCards({ snapshot }: MetricCardsProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <TotalRequestsCard snapshot={snapshot} />
      <CacheHitRateCard snapshot={snapshot} />
      <TokenCostCard snapshot={snapshot} />
      <AvgLatencyCard snapshot={snapshot} />
    </div>
  );
}

/**
 * 最近请求表格组件。
 *
 * 本文件负责展示 dashboard 上的轻量级最近请求列表。它不负责 trace 原始数据
 * 拉取、过滤或详情展开。
 */
import { memo } from 'react';

/**
 * Recent request row shape — lightweight subset from the backend stream.
 * Matches spec §3 "最近请求实时流" columns.
 */
export interface RecentRequest {
  time: string;       // HH:MM:SS
  user: string;
  dept: string;
  cache: boolean;
  latency: string;    // e.g. "37ms"
}

interface RecentRequestsTableProps {
  requests: RecentRequest[];
}

const RequestRow = memo(function RequestRow({ row }: { row: RecentRequest }) {
  return (
    <tr className="border-b border-crt-border text-[12px] font-mono hover:bg-crt-bg-panel transition-colors">
      <td className="p-2 text-crt-fg-dim tabular-nums">{row.time}</td>
      <td className="p-2 text-crt-fg">{row.user}</td>
      <td className="p-2">
        <span className="font-label text-[10px] text-crt-fg-dim tracking-wider">
          {row.dept}
        </span>
      </td>
      <td className="p-2">
        {row.cache ? (
          <span className="text-crt-green font-label text-[9px]">命中</span>
        ) : (
          <span className="text-crt-fg-muted font-label text-[9px]">未命中</span>
        )}
      </td>
      <td className="p-2 tabular-nums">
        <span
          className={
            parseInt(row.latency) < 100
              ? 'text-crt-green'
              : parseInt(row.latency) < 500
              ? 'text-crt-fg'
              : parseInt(row.latency) < 1000
              ? 'text-yellow-500'
              : 'text-crt-red'
          }
        >
          {row.latency}
        </span>
      </td>
    </tr>
  );
});

export function RecentRequestsTable({ requests }: RecentRequestsTableProps) {
  const display = requests.slice(0, 20);

  return (
    <div className="border border-crt-border bg-crt-bg-elevated rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 h-8 border-b border-crt-border">
        <span className="font-label text-crt-fg-muted tracking-[0.12em]">
          最近请求 / 最近 20 条
        </span>
        {display.length > 0 && (
          <span className="font-label text-crt-fg-muted">
            显示 {display.length} 条
          </span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
      <table className="w-full min-w-[620px]">
        <thead>
          <tr className="border-b border-crt-border text-crt-fg-muted">
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[90px]">
              时间
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider">
              用户
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[90px]">
              部门
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[70px]">
              缓存
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[90px]">
              延迟
            </th>
          </tr>
        </thead>
        <tbody>
          {display.length === 0 ? (
            <tr>
              <td
                colSpan={5}
                className="p-4 text-center font-label text-crt-fg-muted"
              >
                暂无最近请求，等待网关数据。
              </td>
            </tr>
          ) : (
            display.map((row, i) => <RequestRow key={i} row={row} />)
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}

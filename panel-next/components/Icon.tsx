const PATHS: Record<string, string> = {
  dashboard: "M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z",
  users: "M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0Zm-12 9a8 8 0 0 1 16 0v1H4v-1Z",
  zivpn: "M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Zm-1 14-3.5-3.5 1.4-1.4L11 13.2l4.1-4.1 1.4 1.4L11 16Z",
  services: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm9 5v-2l-2.1-.7a7 7 0 0 0-.7-1.7l1-2-1.4-1.4-2 1a7 7 0 0 0-1.7-.7L13 3h-2l-.7 2.1a7 7 0 0 0-1.7.7l-2-1L5.2 6.2l1 2a7 7 0 0 0-.7 1.7L3 11v2l2.1.7c.2.6.4 1.2.7 1.7l-1 2 1.4 1.4 2-1c.5.3 1.1.5 1.7.7L11 21h2l.7-2.1c.6-.2 1.2-.4 1.7-.7l2 1 1.4-1.4-1-2c.3-.5.5-1.1.7-1.7L21 13Z",
  logs: "M5 3h14a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm2 5v2h10V8H7Zm0 4v2h10v-2H7Zm0 4v2h6v-2H7Z",
  backups: "M12 3C7 3 3 4.8 3 7v10c0 2.2 4 4 9 4s9-1.8 9-4V7c0-2.2-4-4-9-4Zm0 2c4.4 0 7 1.3 7 2s-2.6 2-7 2-7-1.3-7-2 2.6-2 7-2Zm7 12c0 .7-2.6 2-7 2s-7-1.3-7-2v-2.3C6.6 15.5 9.1 16 12 16s5.4-.5 7-1.3V17Z",
  settings: "M4 6h10v2H4V6Zm12 0h4v2h-4V6Zm-2-2h2v6h-2V4ZM4 16h4v2H4v-2Zm6 0h10v2H10v-2Zm-2-2h2v6H8v-6Z",
  logout: "M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h5v-2H5V5h5V3Zm7 4-1.4 1.4L18.2 11H9v2h9.2l-2.6 2.6L17 17l5-5-5-5Z",
  plus: "M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z",
  search: "M10 3a7 7 0 1 0 4.2 12.6l4.6 4.6 1.4-1.4-4.6-4.6A7 7 0 0 0 10 3Zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10Z",
  copy: "M8 3h10a2 2 0 0 1 2 2v12h-2V5H8V3Zm-3 4h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z",
  cpu: "M9 2h2v2h2V2h2v2h2a2 2 0 0 1 2 2v2h2v2h-2v2h2v2h-2v2a2 2 0 0 1-2 2h-2v2h-2v-2h-2v2H9v-2H7a2 2 0 0 1-2-2v-2H3v-2h2v-2H3V8h2V6a2 2 0 0 1 2-2h2V2Zm-2 6v8h10V8H7Z",
  ram: "M3 7h18v8h-2v2h-2v-2h-2v2h-2v-2h-2v2H9v-2H7v2H5v-2H3V7Zm3 2v3h3V9H6Zm5 0v3h3V9h-3Zm5 0v3h3V9h-3Z",
  disk: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 7a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z",
  clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v5.4l3.7 2.2-1 1.7L11 13V7h2Z",
  wifi: "M12 18.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3ZM2 8.8l1.4 1.4a12 12 0 0 1 17.2 0L22 8.8a14 14 0 0 0-20 0Zm4 4 1.4 1.4a6.5 6.5 0 0 1 9.2 0L18 12.8a8.5 8.5 0 0 0-12 0Z",
  traffic: "M7 3 3 7h3v8h2V7h3L7 3Zm10 18 4-4h-3V9h-2v8h-3l4 4Z",
};

export default function Icon({
  name,
  className = "h-4 w-4",
}: {
  name: keyof typeof PATHS | string;
  className?: string;
}) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d={PATHS[name] ?? PATHS.dashboard} />
    </svg>
  );
}

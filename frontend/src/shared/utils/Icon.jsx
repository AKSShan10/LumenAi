// Small line icons for the sidebar and buttons. Each one is a few SVG paths.
const PATHS = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  people: "M16 11a3 3 0 100-6 3 3 0 000 6zM8 11a3 3 0 100-6 3 3 0 000 6zM2 20c0-3 2.7-5 6-5s6 2 6 5M14 15.3c.6-.2 1.3-.3 2-.3 3.3 0 6 2 6 5",
  calendar: "M4 6h16v15H4zM4 10h16M8 3v5M16 3v5",
  document: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h6M9 17h6",
  chart: "M5 21V10M12 21V4M19 21v-8",
  gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19 12l2-1-1-3-2 .5-1.5-1.5.5-2-3-1-1 2h-2L9 3 6 4l.5 2L5 7.5 3 7l-1 3 2 1v2l-2 1 1 3 2-.5 1.5 1.5-.5 2 3 1 1-2h2l1 2 3-1-.5-2 1.5-1.5 2 .5 1-3-2-1z",
  mail: "M3 6h18v12H3zM3 7l9 6 9-6",
  clip: "M20 11l-8 8a5 5 0 01-7-7l8-8a3.5 3.5 0 015 5l-8 8a2 2 0 01-3-3l7-7",
  send: "M3 11l18-8-8 18-2-8z",
  bulb: "M9 18h6M10 21h4M12 3a6 6 0 00-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0012 3z",
  briefcase: "M3 8h18v12H3zM9 8V5h6v3M3 13h18",
  cap: "M2 9l10-5 10 5-10 5zM6 11.5V16c2 2 10 2 12 0v-4.5",
  clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
  code: "M8 8l-4 4 4 4M16 8l4 4-4 4M13 6l-2 12",
};

export default function Icon({ name, size = 20 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

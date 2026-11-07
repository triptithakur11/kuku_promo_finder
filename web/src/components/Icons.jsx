const I = ({ d, size = 20, ...p }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden {...p}>
    {d}
  </svg>
);

export const Sparkle = (p) => <I {...p} d={<><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z" /><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></>} />;
export const Film = (p) => <I {...p} d={<><rect x="6" y="3" width="12" height="18" rx="2" /><path d="M10 9.5v5l4-2.5z" /></>} />;
export const Upload = (p) => <I {...p} d={<><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" /><path d="M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" /></>} />;
export const FileText = (p) => <I {...p} d={<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>} />;
export const Check = (p) => <I {...p} d={<path d="M5 12.5l4.5 4.5L19 7.5" />} />;
export const X = (p) => <I {...p} d={<path d="M6 6l12 12M18 6L6 18" />} />;
export const Zap = (p) => <I {...p} d={<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z" />} />;
export const Hourglass = (p) => <I {...p} d={<><path d="M7 3h10M7 21h10" /><path d="M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9" /></>} />;
export const Eye = (p) => <I {...p} d={<><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>} />;
export const Shield = (p) => <I {...p} d={<><path d="M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z" /><path d="M9 12l2 2 4-4" /></>} />;
export const Clock = (p) => <I {...p} d={<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>} />;
export const Layers = (p) => <I {...p} d={<><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></>} />;
export const UserCheck = (p) => <I {...p} d={<><circle cx="9" cy="8" r="4" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 11l2 2 4-4" /></>} />;
export const Download = (p) => <I {...p} d={<><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" /><path d="M5 19h14" /></>} />;
export const Search = (p) => <I {...p} d={<><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></>} />;
export const Alert = (p) => <I {...p} d={<><path d="M12 3l10 18H2z" /><path d="M12 10v4M12 17.5v.5" /></>} />;
export const ArrowLeft = (p) => <I {...p} d={<path d="M19 12H5M11 6l-6 6 6 6" />} />;
export const ArrowRight = (p) => <I {...p} d={<path d="M5 12h14M13 6l6 6-6 6" />} />;
export const Crown = (p) => <I {...p} d={<path d="M3 8l4.5 4L12 5l4.5 7L21 8l-2 11H5z" />} />;
export const Lock = (p) => <I {...p} d={<><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>} />;
export const Settings = (p) => <I {...p} d={<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>} />;

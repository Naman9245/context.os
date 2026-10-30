// Small stroke icons (24x24 grid), coloured by currentColor.

type P = { className?: string }

const base = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
}

export const MicIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8" />
  </svg>
)

export const SpeakerIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M11 5 6 9H3v6h3l5 4V5z" />
    <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
  </svg>
)

export const SpeakerOffIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M11 5 6 9H3v6h3l5 4V5z" />
    <path d="m16 9 5 6M21 9l-5 6" />
  </svg>
)

export const StopIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </svg>
)

// -- navigation ------------------------------------------------------------------

export const HomeIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z" />
  </svg>
)

/** Organize: files dropping into the tray. */
export const SortIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M12 4v9m-4-4 4 4 4-4" />
    <path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
  </svg>
)

export const FolderIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2.2h7.4a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
  </svg>
)

export const ChecklistIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="m4 7 1.6 1.6L8.5 5.6M4 15l1.6 1.6 2.9-3" />
    <path d="M12 7h8M12 15h8" />
  </svg>
)

/** Progress: capsule bars, like the weekly chart. */
export const ChartIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <rect x="4" y="11" width="3.5" height="8" rx="1.75" />
    <rect x="10.25" y="5" width="3.5" height="14" rx="1.75" />
    <rect x="16.5" y="8.5" width="3.5" height="10.5" rx="1.75" />
  </svg>
)

export const ChatIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M5 18.5V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H8.5z" />
  </svg>
)

export const GearIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" />
  </svg>
)

/** The round "go there" button's arrow. */
export const ArrowIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M7 17 17 7M9 7h8v8" />
  </svg>
)

// The brand mark: three ascending gradient parallelograms (blue → amber →
// green), ported verbatim from the plugin's LOGO_SVG
// (plugins/qgis_dashboards/icons.py).
// Gradient ids are suffixed so multiple instances on one page don't collide.

let counter = 0;

export function Logo({
  size = 32,
  className,
}: {
  size?: number;
  className?: string;
}) {
  const uid = `logo${counter++}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 -492.481 492.481 492.481"
      role="img"
      aria-label="QGIS Dashboard logo"
      className={className}
    >
      <defs>
        <linearGradient
          id={`${uid}-a`}
          gradientUnits="userSpaceOnUse"
          x1="-36.6002"
          y1="621.3422"
          x2="-17.2782"
          y2="547.7642"
          gradientTransform="matrix(7.8769 0 0 -7.8769 404.0846 4917.9966)"
        >
          <stop offset="0" stopColor="#A7D2F5" />
          <stop offset="1" stopColor="#5E97D0" />
        </linearGradient>
        <linearGradient
          id={`${uid}-b`}
          gradientUnits="userSpaceOnUse"
          x1="-27.0735"
          y1="620.7541"
          x2="-11.7045"
          y2="560.3241"
          gradientTransform="matrix(7.8769 0 0 -7.8769 404.0846 4917.9966)"
        >
          <stop offset="0" stopColor="#F8CDA6" />
          <stop offset="1" stopColor="#E89A5C" />
        </linearGradient>
        <linearGradient
          id={`${uid}-c`}
          gradientUnits="userSpaceOnUse"
          x1="14.0324"
          y1="554.688"
          x2="-10.4176"
          y2="584.028"
          gradientTransform="matrix(7.8769 0 0 -7.8769 404.0846 4917.9966)"
        >
          <stop offset="0" stopColor="#A9DCC2" />
          <stop offset="1" stopColor="#6FB890" />
        </linearGradient>
      </defs>
      <g transform="matrix(1,0,0,-1,0,0)">
        <polygon
          fill={`url(#${uid}-a)`}
          points="25.687,297.141 135.735,0 271.455,0 161.398,297.141"
        />
        <polygon
          fill={`url(#${uid}-b)`}
          points="123.337,394.807 233.409,97.674 369.144,97.674 259.072,394.807"
        />
        <polygon
          fill={`url(#${uid}-c)`}
          points="221.026,492.481 331.083,195.348 466.794,195.348 356.746,492.481"
        />
      </g>
    </svg>
  );
}

export function Wordmark({ size = 32 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <Logo size={size} />
      <span className="display text-[1.15rem] font-semibold tracking-tight">
        QGIS<span className="text-accent"> Dashboard</span>
      </span>
    </span>
  );
}

// The Title Plotter PH section wordmark — same gradient mark, its own name.
export function TpphWordmark({ size = 32 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <Logo size={size} />
      <span className="display text-[1.15rem] font-semibold tracking-tight">
        Title<span className="text-accent"> Plotter PH</span>
      </span>
    </span>
  );
}

// The umbrella wordmark for the root hub — same gradient mark, "QGIS Plugins".
export function HubWordmark({ size = 32 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <Logo size={size} />
      <span className="display text-[1.15rem] font-semibold tracking-tight">
        QGIS<span className="text-accent"> Plugins</span>
      </span>
    </span>
  );
}

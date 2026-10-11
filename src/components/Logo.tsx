interface LogoProps {
  className?: string;
}

/** Logotipo original ExNet Fiber (arquivo PNG em public/assets). Não redesenhar nem recolorir. */
export function Logo({ className = '' }: LogoProps) {
  return (
    <img
      src="/assets/exnet-fiber-logo.png"
      alt="ExNet Fiber"
      width={1616}
      height={1375}
      decoding="async"
      className={`h-auto w-full select-none ${className}`}
      draggable={false}
    />
  );
}

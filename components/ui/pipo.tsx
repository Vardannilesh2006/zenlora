// GradientBackground — "Pipo", made with the 21st.dev Gradient
// Builder and exported as live CSS (the builder's own Copy-CSS background,
// plus its soften-blur and grain passes). Zero dependencies: one <div> that
// fills its parent. Drop it behind your content:
// <div className="relative h-96"><GradientBackground className="absolute inset-0" /></div>
// Remix the source recipe (colors, mode, finish) in the editor:
// https://21st.dev/community/gradients/editor?from=58063e64-512c-42dc-b70f-8f7888ec8067
export function GradientBackground({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={className}
      style={{
        position: "relative",
        overflow: "hidden",
        width: "100%",
        height: "100%",
        containerType: "size",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: "-16cqmin",
          filter: "blur(8cqmin)",
          backgroundColor: "#FAF9EF",
          backgroundImage:
            "url(\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='0.305'/></svg>\"), radial-gradient(circle at 68.1% 46.03%, rgba(230, 176, 147, 1) 0%, rgba(230, 176, 147, 0.844) 10.28%, rgba(230, 176, 147, 0.5) 20.55%, rgba(230, 176, 147, 0.156) 30.83%, rgba(230, 176, 147, 0) 41.1%), radial-gradient(circle at 25.17% 75.99%, rgba(163, 206, 255, 1) 0%, rgba(163, 206, 255, 0.844) 11.15%, rgba(163, 206, 255, 0.5) 22.3%, rgba(163, 206, 255, 0.156) 33.45%, rgba(163, 206, 255, 0) 44.6%), radial-gradient(circle at 53.11% 12.71%, rgba(250, 249, 239, 1) 0%, rgba(250, 249, 239, 0.844) 16.66%, rgba(250, 249, 239, 0.5) 33.33%, rgba(250, 249, 239, 0.156) 49.99%, rgba(250, 249, 239, 0) 66.65%)",
          backgroundSize: "120px 120px, auto, auto, auto",
          backgroundBlendMode: "overlay, normal, normal, normal",
        }}
      />
      <svg
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          opacity: 0.305,
          mixBlendMode: "overlay",
        }}
      >
        <filter id="grain-58063e64">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.8"
            numOctaves="2"
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#grain-58063e64)" />
      </svg>
    </div>
  )
}

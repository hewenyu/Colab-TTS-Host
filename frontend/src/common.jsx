import React, { useEffect, useRef } from "react";
export function Icon({ type = "voice", ...props }) {
  const paths = {
    voice: "M5 10v4m5-8v12m5-15v18m5-12v6",
    check: "m5 12 4 4 10-10",
    material: "M4 5h6l2 3h8v12H4zM8 13h8m-8 3h5",
    training: "M5 18V9m7 9V4m7 14v-6M3 21h19",
    arrow: "m9 5 7 7-7 7",
    lock: "M7 10V7a5 5 0 0 1 10 0v3M5 10h14v11H5z",
    refresh: "M20 7a9 9 0 1 0 1 8M20 3v5h-5",
    play: "m9 5 11 7-11 7z",
    upload: "M12 17V3m-5 5 5-5 5 5M3 16v5h18v-5",
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...props}>
      <path d={paths[type]} />
    </svg>
  );
}
export function ErrorText({ id, children }) {
  return (
    <p id={id} className="field-error" role="alert">
      {children}
    </p>
  );
}
export function Empty({ title, children }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export const date = (ts) =>
  new Date(ts * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
export function Waveform({ samples }) {
  const ref = useRef();
  useEffect(() => {
    const canvas = ref.current;
    const draw = () => {
      const width = canvas.clientWidth || 600,
        height = 76,
        ctx = canvas.getContext("2d");
      canvas.width = width * devicePixelRatio;
      canvas.height = height * devicePixelRatio;
      ctx.scale(devicePixelRatio, devicePixelRatio);
      ctx.strokeStyle = samples ? "#4673cc" : "#c9d6e3";
      ctx.lineWidth = samples ? 2 : 1;
      ctx.beginPath();
      if (!samples?.length) {
        ctx.moveTo(18, height / 2);
        ctx.lineTo(width - 18, height / 2);
      } else {
        const bars = Math.floor((width - 36) / 4),
          step = Math.max(1, Math.floor(samples.length / bars));
        for (let i = 0; i < bars; i++) {
          let max = 0;
          for (
            let j = i * step;
            j < Math.min((i + 1) * step, samples.length);
            j++
          )
            max = Math.max(max, Math.abs(samples[j]));
          const a = Math.max(1, max * 32);
          ctx.moveTo(18 + i * 4, height / 2 - a);
          ctx.lineTo(18 + i * 4, height / 2 + a);
        }
      }
      ctx.stroke();
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [samples]);
  return (
    <canvas id="waveform" ref={ref} height="76" aria-label="生成音频的波形" />
  );
}

export default function Seal({ size = 32 }: { size?: number }) {
  return (
    <div
      className="shrink-0 rounded-md border-[1.5px] border-ink flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <span
        className="font-mono font-bold text-ink"
        style={{ fontSize: size * 0.42, lineHeight: 1 }}
      >
        F/
      </span>
    </div>
  );
}

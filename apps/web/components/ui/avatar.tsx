import { cn } from "@/lib/utils";

const PALETTE = [
  "bg-[#FFE8D6] text-[#9a3412]",
  "bg-[#D9EEFF] text-[#075985]",
  "bg-[#E9E0FF] text-[#5b21b6]",
  "bg-[#FFD9D2] text-[#9f1239]",
  "bg-[#F8D7E8] text-[#9d174d]",
  "bg-[#E4D4F4] text-[#6b21a8]",
  "bg-[#D1FAE5] text-[#065f46]",
  "bg-[#FEF3C7] text-[#92400e]",
];

function initials(name: string) {
  const clean = name.replace(/^@/, "").trim();
  if (!clean) return "?";
  const parts = clean.split(/[.\s_-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

function tone(seed: string) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

export function Avatar({
  name,
  size = "md",
  className,
}: {
  name: string;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold select-none",
        size === "sm" && "h-8 w-8 text-[10px]",
        size === "md" && "h-10 w-10 text-xs",
        size === "lg" && "h-12 w-12 text-sm",
        size === "xl" && "h-24 w-24 text-2xl",
        tone(name),
        className
      )}
      aria-hidden
    >
      {initials(name)}
    </div>
  );
}

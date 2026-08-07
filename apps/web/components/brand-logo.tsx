import Image from "next/image";
import { cn } from "@/lib/utils";

type BrandLogoProps = {
  className?: string;
  /** Image height in px (width scales from logo aspect). */
  height?: number;
  priority?: boolean;
};

/** Official Spark wordmark (play-in-p + REC badge). */
export function BrandLogo({ className, height = 28, priority = false }: BrandLogoProps) {
  // Source art is ~ roughly 3.2:1 wide.
  const width = Math.round(height * 3.2);
  return (
    <Image
      src="/spark-logo.png"
      alt="Spark"
      width={width}
      height={height}
      priority={priority}
      className={cn("h-auto w-auto object-contain", className)}
      style={{ height, width: "auto" }}
    />
  );
}

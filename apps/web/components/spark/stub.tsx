import Link from "next/link";

export default function SparkStub({
  title,
  blurb,
}: {
  title: string;
  blurb: string;
}) {
  return (
    <div className="mx-auto max-w-lg rounded-2xl border border-white/[0.06] bg-[#121212] p-8 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-3 text-sm text-zinc-400">{blurb}</p>
      <Link href="/student-dashboard" className="mt-6 inline-flex text-sm text-[#ff4d00] hover:underline">
        ← Back to dashboard
      </Link>
    </div>
  );
}

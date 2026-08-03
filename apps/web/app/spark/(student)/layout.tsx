"use client";

/** Dark canvas under the shared InstaScope navbar (no second header). */
export default function SparkStudentLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="spark-root -mx-4 -my-6 rounded-none bg-black px-4 py-6 text-white md:-mx-7 md:-my-7 md:px-7 md:py-8">
      {children}
    </div>
  );
}

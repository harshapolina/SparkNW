import SparkStub from "@/components/spark/stub";

const stubs: Record<string, { title: string; blurb: string }> = {
  students: { title: "Students", blurb: "Full student roster management — next iteration." },
  scraped: { title: "Scraped Data", blurb: "Raw Instagram scrape feeds from InstaScope — connect next." },
  submissions: { title: "Submissions", blurb: "Review queue UI — counts already on the admin dashboard." },
  analytics: { title: "Analytics", blurb: "Deep cohort analytics — coming next." },
  milestones: { title: "Milestones", blurb: "Program milestone configuration." },
  rewards: { title: "Rewards", blurb: "Reward catalog and fulfillment." },
  reports: { title: "Reports", blurb: "Exportable program reports." },
  settings: { title: "Settings", blurb: "SPARK admin settings." },
};

export default async function AdminStubPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  const meta = stubs[section] || { title: section, blurb: "Coming soon." };
  return <SparkStub title={meta.title} blurb={meta.blurb} />;
}

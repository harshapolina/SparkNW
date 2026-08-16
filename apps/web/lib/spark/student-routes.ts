/** Student portal URLs include the logged-in student_id so the address bar matches the account. */

export function studentDashboardHref(studentId?: string | null) {
  const sid = String(studentId || "").trim();
  if (!sid) return "/student-dashboard";
  return `/student-dashboard?student_id=${encodeURIComponent(sid)}`;
}

export function withStudentId(path: string, studentId?: string | null) {
  const sid = String(studentId || "").trim();
  if (!sid) return path;
  const [base, qs] = path.split("?");
  const params = new URLSearchParams(qs || "");
  params.set("student_id", sid);
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

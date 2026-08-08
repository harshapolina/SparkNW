/** SPARK programme window — scrapes & metrics start here (inclusive). No date-range UI. */
export const SPARK_COHORT_START = "2026-07-15";

export const PROGRAMME_STARTED_LABEL = "15 Jul 2026";

export function utcTodayYmd(): string {
  const d = new Date();
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Clamp a YYYY-MM-DD into [cohort start, today]. */
export function clampYmdToCohort(ymd: string, today = utcTodayYmd()): string {
  if (!ymd) return SPARK_COHORT_START;
  if (ymd < SPARK_COHORT_START) return SPARK_COHORT_START;
  if (ymd > today) return today;
  return ymd;
}

export function defaultCohortRange(today = utcTodayYmd()): { from: string; to: string } {
  return {
    from: SPARK_COHORT_START,
    to: today < SPARK_COHORT_START ? SPARK_COHORT_START : today,
  };
}

export function parseYmdLocal(ymd: string): Date | undefined {
  if (!ymd || !/^\d{4}-\d{2}-\d{2}$/.test(ymd)) return undefined;
  const [y, m, d] = ymd.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return Number.isNaN(dt.getTime()) ? undefined : dt;
}

function formatYmdShort(ymd: string): string {
  const d = parseYmdLocal(ymd);
  if (!d) return ymd;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function programmeWindowEndYmd(toYmd?: string | null): string {
  return toYmd || utcTodayYmd();
}

export function programmeWindowEndLabel(toYmd?: string | null): string {
  return formatYmdShort(programmeWindowEndYmd(toYmd));
}

/** True when the end of the window is calendar-today (UTC). */
export function isProgrammeWindowLive(toYmd?: string | null): boolean {
  return programmeWindowEndYmd(toYmd) === utcTodayYmd();
}

/** Short line for headers */
export function programmeWindowLine(toYmd?: string | null): string {
  const end = programmeWindowEndLabel(toYmd);
  const live = isProgrammeWindowLive(toYmd);
  return live
    ? `Programme started ${PROGRAMME_STARTED_LABEL} · scored through today (${end}) — end date updates daily`
    : `Programme started ${PROGRAMME_STARTED_LABEL} · data & SPARK points calculated from ${PROGRAMME_STARTED_LABEL} to ${end}`;
}

/** Compact badge text (plain string fallback) */
export function programmeWindowBadge(toYmd?: string | null): string {
  const end = programmeWindowEndLabel(toYmd);
  if (isProgrammeWindowLive(toYmd)) {
    return `${PROGRAMME_STARTED_LABEL} → Today (${end})`;
  }
  return `${PROGRAMME_STARTED_LABEL} → ${end}`;
}

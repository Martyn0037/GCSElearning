// frontend/src/subjects/TopicMapPage.tsx
import { useParams } from "react-router";

import { useGetMyTopicMap } from "../api/generated/endpoints";
import type { UserOut } from "../api/generated/model";
import { ApiError } from "../api/http";
import { AppShell } from "../components/AppShell";
import { ButtonLink, LoadingCards, PageHeader } from "../components/ui";
import { TopicList } from "./TopicList";

/** A subject's topic map for the student. */
export function TopicMapPage({ user }: { user: UserOut }) {
  const { enrolmentId = "" } = useParams();
  const map = useGetMyTopicMap(enrolmentId);
  const back = { to: "/", label: "Back to subjects" };

  return (
    <AppShell user={user}>
      {!map.isSuccess && <PageHeader title="Topics" back={back} />}
      {map.isPending && <LoadingCards rows={4} label="Loading topics…" />}
      {map.isError && (
        <p role="alert" className="rounded-2xl bg-amber-50 p-4 text-amber-900">
          {map.error instanceof ApiError && map.error.code === "SUBJECT_NOT_READY"
            ? "This subject is still being set up. Check back soon."
            : map.error instanceof ApiError && map.error.status === 404
              ? "We couldn't find that subject."
              : "Couldn't load this subject. Please refresh."}
        </p>
      )}
      {map.isSuccess && (
        <>
          <PageHeader
            back={back}
            title={map.data.subjectName}
            subtitle={
              <>
                {map.data.specification.code} · {map.data.specification.version}
                {map.data.tier
                  ? ` · ${map.data.tier === "higher" ? "Higher" : "Foundation"} tier`
                  : ""}
              </>
            }
            action={
              <ButtonLink to={`/progress/${map.data.enrolmentId}`} variant="secondary" icon="chart">
                Progress
              </ButtonLink>
            }
          />
          <TopicList topics={map.data.topics} enrolmentId={map.data.enrolmentId} />
        </>
      )}
    </AppShell>
  );
}

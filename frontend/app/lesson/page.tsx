import { LessonRoom } from "@/components/LessonRoom";
import { requireUserEmail } from "@/lib/session";

export default async function LessonPage() {
  await requireUserEmail();
  return <LessonRoom />;
}

import { Question } from "../lib/types";

export function QuestionPanel({ question }: { question: Question | null }) {
  return (
    <section>
      <h2>Question</h2>
      {question ? (
        <>
          <p>{question.text}</p>
          <p>Difficulty: {question.difficulty}</p>
        </>
      ) : (
        <p>No active question.</p>
      )}
    </section>
  );
}

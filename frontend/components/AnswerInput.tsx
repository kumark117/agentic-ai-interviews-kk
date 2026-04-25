import { FormEvent, useState } from "react";

export function AnswerInput({
  disabled,
  onSubmit
}: {
  disabled: boolean;
  onSubmit: (answerText: string) => Promise<void>;
}) {
  const [answer, setAnswer] = useState("");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!answer.trim()) {
      return;
    }
    await onSubmit(answer);
    setAnswer("");
  }

  return (
    <section>
      <h3>Your Answer</h3>
      <form onSubmit={handleSubmit}>
        <textarea
          rows={6}
          placeholder="Type your answer..."
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          disabled={disabled}
        />
        <button type="submit" disabled={disabled || !answer.trim()}>
          Submit Answer
        </button>
      </form>
    </section>
  );
}

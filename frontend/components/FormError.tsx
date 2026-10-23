/** Inline, polite form error shown under a field. */
export function FormError({ id, message }: { id: string; message: string | null }) {
  if (!message) return null;
  return (
    <p id={id} className="error" role="alert">
      {message}
    </p>
  );
}

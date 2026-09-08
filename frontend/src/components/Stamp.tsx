interface Props { kind: string; label?: string; pressed?: boolean }

/** A verdict, pressed onto the page. Nothing here is decorative: the word is
 *  the decision, and the decision is the product. */
export function Stamp({ kind, label, pressed }: Props) {
  return (
    <span className={`stamp stamp--${kind}${pressed ? " stamp--pressed" : ""}`}>
      {label ?? kind}
    </span>
  );
}

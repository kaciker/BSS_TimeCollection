import { useRef } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
  continueLabel?: string;
  keyboardEntry?: boolean;
}

export function NumericKeypad({ value, onChange, onSubmit, disabled, placeholder = "Enter badge number", continueLabel = "Continue", keyboardEntry = false }: Props) {
  const entryRef = useRef<HTMLInputElement>(null);
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "⌫"];
  const press = (key: string) => {
    if (key === "C") onChange("");
    else if (key === "⌫") onChange(value.slice(0, -1));
    else onChange((value + key).slice(0, 160));
  };

  return (
    <div className="keypad-wrap">
      {keyboardEntry ? (
        <input
          ref={entryRef}
          className={`badge-display badge-display-input${value ? "" : " is-placeholder"}`}
          aria-label={placeholder}
          autoComplete="off"
          autoFocus
          disabled={disabled}
          inputMode="numeric"
          maxLength={160}
          onChange={event => onChange(event.currentTarget.value.replace(/[^0-9]/g, "").slice(0, 160))}
          onKeyDown={event => {
            if (event.key === "Enter" && value && !disabled) {
              event.preventDefault();
              onSubmit();
            }
          }}
          placeholder={placeholder}
          type="text"
          value={value}
        />
      ) : (
        <div className={`badge-display${value ? "" : " is-placeholder"}`} aria-live="polite">{value || placeholder}</div>
      )}
      <div className="keypad">
        {keys.map((key) => (
          <button key={key} className="key" type="button" onMouseDown={event => { if (keyboardEntry) event.preventDefault(); }} onClick={() => { press(key); entryRef.current?.focus(); }} disabled={disabled}>{key}</button>
        ))}
      </div>
      <button className="primary large" type="button" disabled={disabled || !value} onClick={onSubmit}>{continueLabel}</button>
    </div>
  );
}

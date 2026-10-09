interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}

export function NumericKeypad({ value, onChange, onSubmit, disabled }: Props) {
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "⌫"];
  const press = (key: string) => {
    if (key === "C") onChange("");
    else if (key === "⌫") onChange(value.slice(0, -1));
    else onChange((value + key).slice(0, 160));
  };

  return (
    <div className="keypad-wrap">
      <div className="badge-display">{value || "Enter badge number"}</div>
      <div className="keypad">
        {keys.map((key) => (
          <button key={key} className="key" type="button" onClick={() => press(key)} disabled={disabled}>
            {key}
          </button>
        ))}
      </div>
      <button className="primary large" type="button" disabled={disabled || !value} onClick={onSubmit}>
        Continue
      </button>
    </div>
  );
}

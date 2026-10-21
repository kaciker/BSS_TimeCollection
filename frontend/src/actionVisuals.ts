// Shared local visual catalogue for administration and terminal actions.
import type { Language } from "./i18n";
import { translate } from "./i18n";

export const actionVisuals = [
  {
    "key": "",
    "name": "No illustration"
  },
  {
    "key": "end-work",
    "name": "End work"
  },
  {
    "key": "break",
    "name": "Break"
  },
  {
    "key": "factory",
    "name": "Factory exit"
  },
  {
    "key": "no-work",
    "name": "No work"
  },
  {
    "key": "medical",
    "name": "Medical"
  },
  {
    "key": "personal",
    "name": "Personal matters"
  },
  {
    "key": "legal",
    "name": "Legal matters"
  },
  {
    "key": "bocadillo",
    "name": "Bocadillo"
  },
  {
    "key": "comida",
    "name": "Comida"
  },
  {
    "key": "medico-empresa",
    "name": "Médico de empresa"
  },
  {
    "key": "formacion",
    "name": "Formación"
  },
  {
    "key": "no-productivo",
    "name": "No productivo"
  },
  {
    "key": "comite-empresa",
    "name": "Comité de empresa"
  },
  {
    "key": "trabajo-fuera-fabrica",
    "name": "Trabajo fuera de fábrica"
  },
  {
    "key": "medico",
    "name": "Médico"
  },
  {
    "key": "viaje-empresa",
    "name": "Viaje de empresa"
  },
  {
    "key": "examenes",
    "name": "Exámenes"
  },
  {
    "key": "mutua-accidente",
    "name": "Mutua / accidente"
  },
  {
    "key": "comite-seguridad-salud",
    "name": "Comité de seguridad y salud"
  },
  {
    "key": "formacion-fuera-jornada",
    "name": "Formación fuera de jornada"
  },
  {
    "key": "salida-sindical",
    "name": "Salida sindical"
  },
  {
    "key": "huelga",
    "name": "Huelga"
  },
  {
    "key": "acompanamiento-medico",
    "name": "Acompañamiento médico"
  }
];

const visualTranslationKeys: Record<string, string> = {
  "": "visualNoIllustration", "end-work": "visualEndWork", "break": "visualBreak", factory: "visualFactoryExit", "no-work": "visualNoWork",
  medical: "visualMedical", personal: "visualPersonal", legal: "visualLegal", bocadillo: "visualSnack", comida: "visualMeal",
  "medico-empresa": "visualCompanyDoctor", formacion: "visualTraining", "no-productivo": "visualNonProductive", "comite-empresa": "visualWorksCouncil",
  "trabajo-fuera-fabrica": "visualOffsiteWork", medico: "visualDoctor", "viaje-empresa": "visualBusinessTrip", examenes: "visualExams",
  "mutua-accidente": "visualInsuranceAccident", "comite-seguridad-salud": "visualHealthSafetyCommittee", "formacion-fuera-jornada": "visualOffHoursTraining",
  "salida-sindical": "visualUnionLeave", huelga: "visualStrike", "acompanamiento-medico": "visualMedicalEscort",
};
export function localizedActionVisuals(language: Language) {
  return actionVisuals.map(visual => ({ ...visual, name: translate(language, visualTranslationKeys[visual.key] ?? visual.name) }));
}

export const actionVisualKeys = new Set(actionVisuals.filter(visual => visual.key).map(visual => visual.key));

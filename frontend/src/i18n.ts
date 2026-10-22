import { useEffect, useState } from "react";

export type Language = "en" | "fr" | "es" | "pl";

const STORAGE_KEY = "bss-timecollection-language";
const EVENT_NAME = "bss-language-change";

export const languageOptions: { value: Language; label: string }[] = [
  { value: "en", label: "English" },
  { value: "fr", label: "Français" },
  { value: "es", label: "Español" },
  { value: "pl", label: "Polski" },
];

const strings: Record<Language, Record<string, string>> = {
  en: {
    duplicateRecorded: "Scan already recorded", alreadyInsideFactory: "Badge already inside factory", alreadyOutsideFactory: "Badge already outside factory",
    administration: "Administration", operations: "OPERATIONS", configuration: "CONFIGURATION",
    badgeStatus: "Badge status", eventLogs: "Event logs", transmissionLogs: "Transmission logs", terminals: "Terminals", actions: "Actions", database: "Database", settings: "Settings",
    badgeStatusDesc: "Current local state of each badge, derived from its latest captured event.", eventLogsDesc: "Inspect captured events, stored facts and Oracle delivery status.", transmissionLogsDesc: "Review every Oracle transmission attempt and its recorded response.", terminalsDesc: "Manage factory clocks, identification methods and assigned worker actions.", actionsDesc: "Configure worker actions, hierarchical exit reasons and Oracle supplier event mappings.", databaseDesc: "Inspect the primary database and validate a managed external PostgreSQL target.", settingsDesc: "Configure user-interface preferences for this browser.",
    loadingConfiguration: "Loading configuration…", retry: "Retry", language: "Language", languageHelp: "Choose the interface language used by this browser. Technical codes and Oracle mappings are never translated.", languageSaved: "Language preference is stored locally in this browser.",
    terminalActivation: "TERMINAL ACTIVATION", pairBrowser: "Pair this browser", pairHelp: "Enter this temporary code in Administration and assign it to the terminal you want to use.", waitingActivation: "Waiting for activation…", codeExpires: "This code expires at", terminalNotProvisioned: "Terminal not provisioned", pairingAlternative: "You can still use the existing one-time activation link, or generate a new pairing code from this browser.", generatePairing: "Generate pairing code", loadingTerminal: "Loading terminal…",
    exitMenuTimeout: "Exit menu timeout", exitMenuTimeoutHelp: "Return to identification if nobody chooses an exit reason.", secondsBeforeReturn: "Seconds before return", exitMenuTimeoutNote: "Use 0 to disable. New and cloned terminals start at 5 seconds; range 0–120.", eventDetails: "Event details", loadingDetails: "Loading details…", closeDetails: "Close details",
    entryRegistered: "Entry registered", exitRegistered: "Exit registered", eventStored: "Your event has been stored.", exit: "EXIT", selectExit: "Select the reason for leaving", selectSubaction: "Select the specific reason", cancel: "Cancel", identification: "IDENTIFICATION", presentBadge: "Present your badge", keypadNote: "Enter your badge manually or present your card.", presentCard: "Present your card", readingCard: "Reading card…", enterBadge: "Enter badge number", continue: "Continue",
  },
  fr: {
    duplicateRecorded: "Lecture déjà enregistrée", alreadyInsideFactory: "Carte déjà dans la fabrique", alreadyOutsideFactory: "Carte déjà hors de la fabrique",
    administration: "Administration", operations: "OPÉRATIONS", configuration: "CONFIGURATION",
    badgeStatus: "État des badges", eventLogs: "Journal des événements", transmissionLogs: "Journal des transmissions", terminals: "Terminaux", actions: "Actions", database: "Base de données", settings: "Paramètres",
    badgeStatusDesc: "État local actuel de chaque badge selon le dernier événement enregistré.", eventLogsDesc: "Consulter les événements enregistrés et leur état d'envoi vers Oracle.", transmissionLogsDesc: "Consulter chaque tentative de transmission Oracle et sa réponse.", terminalsDesc: "Gérer les pointeuses, les méthodes d'identification et les actions disponibles.", actionsDesc: "Configurer les actions, les motifs de sortie hiérarchiques et les correspondances Oracle.", databaseDesc: "Consulter la base principale et valider une base PostgreSQL externe.", settingsDesc: "Configurer les préférences d'interface de ce navigateur.",
    loadingConfiguration: "Chargement de la configuration…", retry: "Réessayer", language: "Langue", languageHelp: "Choisissez la langue de l'interface pour ce navigateur. Les codes techniques et les correspondances Oracle ne sont jamais traduits.", languageSaved: "La préférence de langue est enregistrée localement dans ce navigateur.",
    terminalActivation: "ACTIVATION DU TERMINAL", pairBrowser: "Associer ce navigateur", pairHelp: "Saisissez ce code temporaire dans l'administration et affectez-le au terminal souhaité.", waitingActivation: "En attente d'activation…", codeExpires: "Ce code expire à", terminalNotProvisioned: "Terminal non configuré", pairingAlternative: "Vous pouvez utiliser le lien d'activation à usage unique ou générer un nouveau code d'association.", generatePairing: "Générer un code", loadingTerminal: "Chargement du terminal…",
    exitMenuTimeout: "Délai du menu de sortie", exitMenuTimeoutHelp: "Retour à l’identification si aucun motif de sortie n’est choisi.", secondsBeforeReturn: "Secondes avant le retour", exitMenuTimeoutNote: "Utilisez 0 pour désactiver. Les nouveaux terminaux et les copies commencent à 5 secondes ; plage 0–120.", eventDetails: "Détails de l’événement", loadingDetails: "Chargement des détails…", closeDetails: "Fermer les détails",
    entryRegistered: "Entrée enregistrée", exitRegistered: "Sortie enregistrée", eventStored: "Votre événement a été enregistré.", exit: "SORTIE", selectExit: "Sélectionnez le motif de sortie", selectSubaction: "Sélectionnez le motif précis", cancel: "Annuler", identification: "IDENTIFICATION", presentBadge: "Présentez votre badge", keypadNote: "Saisissez votre badge ou présentez votre carte.", presentCard: "Présentez votre carte", readingCard: "Lecture de la carte…", enterBadge: "Saisissez le numéro de badge", continue: "Continuer",
  },
  es: {
    duplicateRecorded: "Fichaje ya registrado", alreadyInsideFactory: "Tarjeta ya dentro de fábrica", alreadyOutsideFactory: "Tarjeta ya fuera de fábrica",
    administration: "Administración", operations: "OPERACIONES", configuration: "CONFIGURACIÓN",
    badgeStatus: "Estado de tarjetas", eventLogs: "Registro de eventos", transmissionLogs: "Registro de transmisiones", terminals: "Terminales", actions: "Acciones", database: "Base de datos", settings: "Configuración",
    badgeStatusDesc: "Estado local actual de cada tarjeta según su último evento registrado.", eventLogsDesc: "Consulta los eventos capturados y su estado de envío a Oracle.", transmissionLogsDesc: "Revisa cada intento de transmisión a Oracle y su respuesta.", terminalsDesc: "Gestiona terminales, métodos de identificación y acciones disponibles.", actionsDesc: "Configura acciones, motivos de salida jerárquicos y mapeos de eventos Oracle.", databaseDesc: "Consulta la base principal y valida una PostgreSQL externa gestionada.", settingsDesc: "Configura las preferencias de interfaz de este navegador.",
    loadingConfiguration: "Cargando configuración…", retry: "Reintentar", language: "Idioma", languageHelp: "Elige el idioma de la interfaz para este navegador. Los códigos técnicos y los mapeos de Oracle no se traducen.", languageSaved: "La preferencia de idioma se guarda localmente en este navegador.",
    terminalActivation: "ACTIVACIÓN DEL TERMINAL", pairBrowser: "Vincular este navegador", pairHelp: "Introduce este código temporal en Administración y asígnalo al terminal que quieras utilizar.", waitingActivation: "Esperando activación…", codeExpires: "Este código caduca a las", terminalNotProvisioned: "Terminal no provisionado", pairingAlternative: "Puedes seguir usando el enlace de activación de un solo uso o generar un nuevo código de vinculación.", generatePairing: "Generar código", loadingTerminal: "Cargando terminal…",
    exitMenuTimeout: "Tiempo de espera del menú de salida", exitMenuTimeoutHelp: "Volverá a identificación si nadie elige un motivo de salida.", secondsBeforeReturn: "Segundos antes de volver", exitMenuTimeoutNote: "Usa 0 para desactivar. Los terminales nuevos y clonados empiezan en 5 segundos; rango 0–120.", eventDetails: "Detalles del evento", loadingDetails: "Cargando detalles…", closeDetails: "Cerrar detalles",
    entryRegistered: "Entrada registrada", exitRegistered: "Salida registrada", eventStored: "El evento se ha guardado.", exit: "SALIDA", selectExit: "Selecciona el motivo de salida", selectSubaction: "Selecciona el motivo específico", cancel: "Cancelar", identification: "IDENTIFICACIÓN", presentBadge: "Presenta tu tarjeta", keypadNote: "Introduce tu tarjeta manualmente o acércala al lector.", presentCard: "Presenta tu tarjeta", readingCard: "Leyendo tarjeta…", enterBadge: "Introduce el número de tarjeta", continue: "Continuar",
  },
  pl: {
    duplicateRecorded: "Odczyt już zapisany", alreadyInsideFactory: "Karta już wewnątrz fabryki", alreadyOutsideFactory: "Karta już poza fabryką",
    administration: "Administracja", operations: "OPERACJE", configuration: "KONFIGURACJA",
    badgeStatus: "Status kart", eventLogs: "Dziennik zdarzeń", transmissionLogs: "Dziennik transmisji", terminals: "Terminale", actions: "Akcje", database: "Baza danych", settings: "Ustawienia",
    badgeStatusDesc: "Aktualny lokalny status każdej karty na podstawie ostatniego zdarzenia.", eventLogsDesc: "Przeglądaj zapisane zdarzenia i status wysyłki do Oracle.", transmissionLogsDesc: "Przeglądaj próby transmisji do Oracle i ich odpowiedzi.", terminalsDesc: "Zarządzaj terminalami, metodami identyfikacji i dostępnymi akcjami.", actionsDesc: "Konfiguruj akcje, hierarchiczne powody wyjścia i mapowanie Oracle.", databaseDesc: "Sprawdź główną bazę i zweryfikuj zewnętrzną bazę PostgreSQL.", settingsDesc: "Skonfiguruj preferencje interfejsu dla tej przeglądarki.",
    loadingConfiguration: "Ładowanie konfiguracji…", retry: "Ponów", language: "Język", languageHelp: "Wybierz język interfejsu dla tej przeglądarki. Kody techniczne i mapowania Oracle nie są tłumaczone.", languageSaved: "Preferencja języka jest zapisywana lokalnie w tej przeglądarce.",
    terminalActivation: "AKTYWACJA TERMINALA", pairBrowser: "Połącz tę przeglądarkę", pairHelp: "Wprowadź ten tymczasowy kod w Administracji i przypisz go do wybranego terminala.", waitingActivation: "Oczekiwanie na aktywację…", codeExpires: "Kod wygasa o", terminalNotProvisioned: "Terminal nie jest skonfigurowany", pairingAlternative: "Możesz użyć jednorazowego linku aktywacyjnego lub wygenerować nowy kod parowania.", generatePairing: "Generuj kod", loadingTerminal: "Ładowanie terminala…",
    exitMenuTimeout: "Czas oczekiwania menu wyjścia", exitMenuTimeoutHelp: "Powrót do identyfikacji, jeśli nikt nie wybierze powodu wyjścia.", secondsBeforeReturn: "Sekundy do powrotu", exitMenuTimeoutNote: "Wpisz 0, aby wyłączyć. Nowe terminale i kopie zaczynają od 5 sekund; zakres 0–120.", eventDetails: "Szczegóły zdarzenia", loadingDetails: "Ładowanie szczegółów…", closeDetails: "Zamknij szczegóły",
    entryRegistered: "Wejście zapisane", exitRegistered: "Wyjście zapisane", eventStored: "Zdarzenie zostało zapisane.", exit: "WYJŚCIE", selectExit: "Wybierz powód wyjścia", selectSubaction: "Wybierz dokładny powód", cancel: "Anuluj", identification: "IDENTYFIKACJA", presentBadge: "Przyłóż kartę", keypadNote: "Wprowadź numer karty ręcznie lub przyłóż kartę.", presentCard: "Przyłóż kartę", readingCard: "Odczytywanie karty…", enterBadge: "Wprowadź numer karty", continue: "Dalej",
  },
};

export function getLanguage(): Language {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === "fr" || value === "es" || value === "pl" ? value : "en";
}

export function setLanguage(value: Language): void {
  localStorage.setItem(STORAGE_KEY, value);
  document.documentElement.lang = value;
  window.dispatchEvent(new Event(EVENT_NAME));
}

export function translate(language: Language, key: string): string {
  return strings[language][key] ?? strings.en[key] ?? key;
}

export function useLanguage() {
  const [language, setCurrent] = useState<Language>(getLanguage);
  useEffect(() => {
    document.documentElement.lang = language;
    const changed = () => setCurrent(getLanguage());
    window.addEventListener(EVENT_NAME, changed);
    return () => window.removeEventListener(EVENT_NAME, changed);
  }, [language]);
  return { language, setLanguage, t: (key: string) => translate(language, key) };
}

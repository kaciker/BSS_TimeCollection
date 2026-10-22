import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";
import type { AdminTerminal } from "../types";
import { EventInspector } from "./EventInspector";
import { dateLabel, Status } from "./monitoringTypes";
import type { AttemptSummary, CardState, EventDetail, EventSnapshot, Page } from "./monitoringTypes";
import { useLanguage } from "../i18n";

type View = "cards" | "events" | "attempts";
const statuses = ["PENDING", "SENDING", "RETRY", "SENT", "REJECTED", "UNKNOWN"];
const initialFilters = { clock: "", badge: "", state: "", factoryState: "", status: "", start: "", end: "" };
const pageSize = 50;

export function MonitoringPanel({ terminals, initialView = "cards", onNavigate }: { terminals: AdminTerminal[]; initialView?: View; onNavigate?: (view: View, query?: string) => void }) {
  const { t } = useLanguage();
  const [view, setView] = useState<View>(initialView);
  const [draft, setDraft] = useState(() => {
    const query = new URLSearchParams(window.location.search);
    return { ...initialFilters, badge: query.get("badge") ?? "", clock: query.get("clock") ?? "" };
  });
  const [filters, setFilters] = useState(draft);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Page<EventSnapshot | CardState | AttemptSummary>>({ items: [], total: 0 });
  const [factoryEnabled, setFactoryEnabled] = useState(false);
  const [dataView, setDataView] = useState<View>(initialView);
  const items = dataView === view ? data.items : [];
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState<string | null>(null);
  const [historicalClocks, setHistoricalClocks] = useState<string[]>([]);
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailRequest = useRef(0);
  const detailDialog = useRef<HTMLDialogElement>(null);
  const detailOpen = detailLoading || !!detail;

  useEffect(() => {
    const dialog = detailDialog.current;
    if (!dialog) return;
    const previousOverflow = document.body.style.overflow;
    if (detailOpen) {
      if (!dialog.open) {
        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "");
      }
      document.body.style.overflow = "hidden";
    } else {
      if (dialog.open) {
        if (typeof dialog.close === "function") dialog.close();
        else dialog.removeAttribute("open");
      }
      document.body.style.overflow = previousOverflow;
    }
    return () => { if (detailOpen) document.body.style.overflow = previousOverflow; };
  }, [detailOpen]);

  useEffect(() => {
    void api.get<string[]>("/api/v1/admin/monitoring/clocks").then(setHistoricalClocks).catch(() => {});
  }, []);
  const activeCodes = new Set(terminals.map(terminal => terminal.code));
  const removedCodes = historicalClocks.filter(code => !activeCodes.has(code));

  useEffect(() => {
    let active = true;
    let pending = false;
    const query = new URLSearchParams({ offset: String(offset), limit: String(pageSize) });
    if (filters.clock) query.set("terminal_code", filters.clock);
    if (filters.badge) query.set("reporter_id", filters.badge);
    if (view === "cards" && filters.state) query.set("worker_state", filters.state);
    if (view === "cards" && filters.factoryState) query.set("factory_state", filters.factoryState);
    if (view !== "cards" && filters.status) query.set(view === "events" ? "delivery_status" : "result", filters.status);
    if (view === "events") {
      if (filters.start) query.set("start", new Date(filters.start).toISOString());
      if (filters.end) query.set("end", new Date(filters.end).toISOString());
    }
    setData({ items: [], total: 0 });
    setLoading(true);
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await api.get<Page<EventSnapshot | CardState | AttemptSummary>>(`/api/v1/admin/monitoring/${view}?${query}`);
        if (active) { setData(result); if (view === "cards") setFactoryEnabled(!!result.factory_perimeter_enabled); setDataView(view); setError(""); setUpdated(new Date().toISOString()); }
      } catch (err) { if (active) setError((err as Error).message); }
      finally { pending = false; if (active) setLoading(false); }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 15000);
    return () => { active = false; window.clearInterval(interval); };
  }, [view, filters, offset, revision]);

  const selectView = (next: View) => { setView(next); setOffset(0); closeDetail(); };
  const apply = (event: FormEvent) => { event.preventDefault(); setFilters({ ...draft }); setOffset(0); };
  const closeDetail = () => { detailRequest.current++; setDetail(null); setDetailLoading(false); };
  const inspect = async (id: string) => {
    const request = ++detailRequest.current;
    setDetail(null); setDetailLoading(true);
    try {
      const result = await api.get<EventDetail>(`/api/v1/admin/monitoring/events/${encodeURIComponent(id)}`);
      if (request === detailRequest.current) setDetail(result);
    } catch (err) { if (request === detailRequest.current) setError((err as Error).message); }
    finally { if (request === detailRequest.current) setDetailLoading(false); }
  };
  const history = (badge: string) => {
    const next = { ...filters, badge, start: "", end: "", status: "" };
    if (onNavigate) {
      onNavigate("events", `?badge=${encodeURIComponent(badge)}&clock=${encodeURIComponent(filters.clock)}`);
    } else { setDraft(next); setFilters(next); selectView("events"); }
  };
  const badgeStatus = (value: string) => <span className={`status ${value === "INSIDE" ? "status-sent" : ""}`}>{value === "INSIDE" ? "Inside" : "Outside"}</span>;

  return <>
    <section className="admin-card monitoring">
      <div className="monitor-heading"><div><h2>{view === "cards" ? "Badge register" : view === "events" ? "Captured events" : "Delivery attempts"}</h2></div><button className="secondary" onClick={() => setRevision(value => value + 1)}>Refresh</button></div>
      <form className="monitor-filters" onSubmit={apply}>
        <label>Clock<select value={draft.clock} onChange={e => setDraft({ ...draft, clock: e.target.value })}><option value="">All clocks</option>{terminals.map(terminal => <option key={terminal.code} value={terminal.code}>{terminal.code} · {terminal.name}</option>)}{removedCodes.map(code => <option key={code} value={code}>{code} · removed</option>)}</select></label>
        <label>Badge number<input value={draft.badge} placeholder="Search badge" onChange={e => setDraft({ ...draft, badge: e.target.value })} /></label>
        {view === "cards" ? <label>Estado de célula<select value={draft.state} onChange={e => setDraft({ ...draft, state: e.target.value })}><option value="">All</option><option value="INSIDE">Inside</option><option value="OUTSIDE">Outside</option></select></label> : <label>{view === "events" ? "Delivery" : "Attempt result"}<select value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value })}><option value="">All</option>{(view === "events" ? [...statuses,"LOCAL_ONLY"] : statuses).map(status => <option key={status}>{status}</option>)}</select></label>}
        {view === "cards" && factoryEnabled && <label>Estado de fábrica<select value={draft.factoryState} onChange={e => setDraft({ ...draft, factoryState: e.target.value })}><option value="">Todos</option><option value="INSIDE">Dentro</option><option value="OUTSIDE">Fuera</option></select></label>}
        {view === "events" && <><label>F…5556 tokens truncated…"You can still use the existing one-time activation link, or generate a new pairing code from this browser.", generatePairing: "Generate pairing code", loadingTerminal: "Loading terminal…",
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

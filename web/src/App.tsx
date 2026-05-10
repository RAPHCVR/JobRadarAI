import {
  AlertTriangle,
  BriefcaseBusiness,
  CalendarClock,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileText,
  LogOut,
  MessageSquareText,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader } from "./components/ui/card";
import { Input } from "./components/ui/input";
import { Select } from "./components/ui/select";
import { Textarea } from "./components/ui/textarea";
import { cn } from "./lib/utils";
import type { ApplicationStatus, FitStatus, JobItem, Summary, UserPriority } from "./types";

const statusOptions: Array<{ value: ApplicationStatus; label: string }> = [
  { value: "to_review", label: "A trier" },
  { value: "interested", label: "Interessant" },
  { value: "applied", label: "Postule" },
  { value: "follow_up", label: "Relance" },
  { value: "interview", label: "Entretien" },
  { value: "offer", label: "Offre" },
  { value: "rejected", label: "Refuse" },
  { value: "archived", label: "Archive" },
];

const fitOptions: Array<{ value: FitStatus; label: string }> = [
  { value: "unknown", label: "Fit inconnu" },
  { value: "strong", label: "Fit fort" },
  { value: "ok", label: "Fit OK" },
  { value: "stretch", label: "Stretch" },
  { value: "low", label: "Faible" },
  { value: "blocked", label: "Bloque" },
];

const priorityOptions: Array<{ value: UserPriority; label: string }> = [
  { value: "normal", label: "Normal" },
  { value: "high", label: "Haute" },
  { value: "urgent", label: "Urgent" },
  { value: "low", label: "Basse" },
];

type Filters = {
  q: string;
  bucket: string;
  application_status: string;
  market: string;
  link_status: string;
  active: string;
  sort: string;
};

const emptyFilters: Filters = {
  q: "",
  bucket: "",
  application_status: "",
  market: "",
  link_status: "",
  active: "1",
  sort: "priority",
};

type Notice = { type: "success" | "error"; message: string };

export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [view, setView] = useState<"pipeline" | "queue" | "cv">("pipeline");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);

  const selectedJob = useMemo(
    () => jobs.find((job) => job.stable_id === selectedId) ?? jobs[0],
    [jobs, selectedId]
  );

  useEffect(() => {
    void checkSession();
  }, []);

  useEffect(() => {
    if (authenticated) {
      void reload();
    }
  }, [authenticated, filters]);

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(null), 2800);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(path, { ...init, headers, credentials: "include" });
    if (response.status === 401) {
      setAuthenticated(false);
      throw new Error("Authentification requise");
    }
    const payload = (await response.json()) as T & { error?: string };
    if (!response.ok) {
      throw new Error(payload.error || `Erreur HTTP ${response.status}`);
    }
    return payload;
  }

  async function checkSession() {
    try {
      const payload = await api<{ authenticated: boolean }>("/api/session");
      setAuthenticated(payload.authenticated);
    } catch {
      setAuthenticated(false);
    }
  }

  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api<{ authenticated: boolean }>("/api/login", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setPassword("");
      setAuthenticated(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connexion impossible");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await api<{ authenticated: boolean }>("/api/logout", { method: "POST" });
    setAuthenticated(false);
  }

  async function reload() {
    setBusy(true);
    setError("");
    try {
      const query = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value) query.set(key, value);
      });
      query.set("limit", "500");
      const [summaryPayload, jobsPayload] = await Promise.all([
        api<Summary>("/api/summary"),
        api<{ items: JobItem[]; count: number }>(`/api/jobs?${query.toString()}`),
      ]);
      setSummary(summaryPayload);
      setJobs(jobsPayload.items);
      if (jobsPayload.items.length && !jobsPayload.items.some((job) => job.stable_id === selectedId)) {
        setSelectedId(jobsPayload.items[0].stable_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chargement impossible");
    } finally {
      setBusy(false);
    }
  }

  async function patchJob(job: JobItem, patch: Partial<JobItem>) {
    try {
      const payload = await api<{ job: JobItem }>(`/api/jobs/${job.stable_id}/state`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setJobs((current) => current.map((item) => (item.stable_id === job.stable_id ? payload.job : item)));
      setSelectedId(job.stable_id);
      setNotice({ type: "success", message: "Modification sauvegardee." });
    } catch (err) {
      setNotice({ type: "error", message: err instanceof Error ? err.message : "Sauvegarde impossible." });
    }
  }

  async function addEvent(job: JobItem, note: string) {
    if (!note.trim()) return;
    try {
      const payload = await api<{ job: JobItem }>(`/api/jobs/${job.stable_id}/events`, {
        method: "POST",
        body: JSON.stringify({ type: "note", note }),
      });
      setJobs((current) => current.map((item) => (item.stable_id === job.stable_id ? payload.job : item)));
      setSelectedId(job.stable_id);
      setNotice({ type: "success", message: "Note ajoutee a la timeline." });
    } catch (err) {
      setNotice({ type: "error", message: err instanceof Error ? err.message : "Ajout de note impossible." });
    }
  }

  async function copyToClipboard(text: string, label = "Texte") {
    if (!text.trim()) {
      setNotice({ type: "error", message: "Aucun contenu a copier." });
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setNotice({ type: "success", message: `${label} copie.` });
    } catch {
      setNotice({ type: "error", message: "Copie impossible depuis ce navigateur." });
    }
  }

  if (authenticated === null) {
    return <ShellLoading />;
  }
  if (!authenticated) {
    return <LoginScreen busy={busy} error={error} password={password} setPassword={setPassword} onSubmit={login} />;
  }

  const markets = Object.keys(summary?.market_counts || {}).sort();
  const linkStatuses = Object.keys(summary?.link_status_counts || {}).sort();

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-card/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <h1 className="truncate text-lg font-semibold">JobRadarAI</h1>
              {summary?.run_name ? <Badge variant="outline">{summary.run_name}</Badge> : null}
            </div>
            <p className="truncate text-sm text-muted-foreground">
              {summary?.queue_count ?? jobs.length} offres en queue · {summary?.new_jobs ?? 0} nouvelles ·{" "}
              {summary?.audit?.sources_ok ?? 0} sources OK
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void reload()} disabled={busy}>
              <RefreshCw className={cn("h-4 w-4", busy && "animate-spin")} />
              Actualiser
            </Button>
            {summary?.links?.vie_queue_markdown ? (
              <Button variant="outline" size="sm" onClick={() => openLink(summary.links?.vie_queue_markdown)}>
                <BriefcaseBusiness className="h-4 w-4" />
                VIE
              </Button>
            ) : null}
            <Button variant="ghost" size="icon" aria-label="Deconnexion" onClick={() => void logout()}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1680px] gap-4 px-4 py-4 lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)_430px]">
        <aside className="space-y-4 lg:sticky lg:top-[78px] lg:self-start">
          <SummaryCards summary={summary} />
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Search className="h-4 w-4" />
                Filtres
              </div>
              <Button size="sm" variant="ghost" onClick={() => setFilters(emptyFilters)}>
                Reset
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input
                aria-label="Recherche dans les offres"
                placeholder="Titre, entreprise, signal..."
                value={filters.q}
                onChange={(event) => setFilters({ ...filters, q: event.target.value })}
              />
              <Select aria-label="Filtrer par bucket" value={filters.bucket} onChange={(event) => setFilters({ ...filters, bucket: event.target.value })}>
                <option value="">Tous buckets</option>
                <option value="apply_now">Apply now</option>
                <option value="shortlist">Shortlist</option>
                <option value="high_score">High score</option>
                <option value="maybe">Maybe</option>
              </Select>
              <Select
                aria-label="Filtrer par statut de candidature"
                value={filters.application_status}
                onChange={(event) => setFilters({ ...filters, application_status: event.target.value })}
              >
                <option value="">Tous statuts</option>
                {statusOptions.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </Select>
              <Select aria-label="Filtrer par pays" value={filters.market} onChange={(event) => setFilters({ ...filters, market: event.target.value })}>
                <option value="">Tous pays</option>
                {markets.map((market) => (
                  <option key={market} value={market}>
                    {market}
                  </option>
                ))}
              </Select>
              <Select
                aria-label="Filtrer par statut du lien"
                value={filters.link_status}
                onChange={(event) => setFilters({ ...filters, link_status: event.target.value })}
              >
                <option value="">Tous liens</option>
                {linkStatuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </Select>
              <Select aria-label="Filtrer les offres actives" value={filters.active} onChange={(event) => setFilters({ ...filters, active: event.target.value })}>
                <option value="1">Actives uniquement</option>
                <option value="">Actives + stale</option>
              </Select>
              <Select aria-label="Trier les offres" value={filters.sort} onChange={(event) => setFilters({ ...filters, sort: event.target.value })}>
                <option value="priority">Tri radar</option>
                <option value="score">Score decroissant</option>
                <option value="updated">Dernieres notes</option>
              </Select>
              {error ? <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">{error}</p> : null}
            </CardContent>
          </Card>
        </aside>

        <section className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant={view === "pipeline" ? "default" : "outline"} size="sm" onClick={() => setView("pipeline")}>
                <BriefcaseBusiness className="h-4 w-4" />
                Pipeline
              </Button>
              <Button variant={view === "queue" ? "default" : "outline"} size="sm" onClick={() => setView("queue")}>
                <MessageSquareText className="h-4 w-4" />
                Queue
              </Button>
              <Button variant={view === "cv" ? "default" : "outline"} size="sm" onClick={() => setView("cv")}>
                <FileText className="h-4 w-4" />
                CV
              </Button>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <SlidersHorizontal className="h-4 w-4" />
              {jobs.length} offres affichees
            </div>
          </div>

          {view === "pipeline" ? (
            <Pipeline jobs={jobs} selectedId={selectedJob?.stable_id} onSelect={setSelectedId} onPatch={patchJob} />
          ) : null}
          {view === "queue" ? <Queue jobs={jobs} selectedId={selectedJob?.stable_id} onSelect={setSelectedId} /> : null}
          {view === "cv" ? <CvPanel summary={summary} /> : null}
        </section>

        <DetailPanel job={selectedJob} onPatch={patchJob} onAddEvent={addEvent} onCopyText={copyToClipboard} />
      </main>
      <NoticeToast notice={notice} />
    </div>
  );
}

function ShellLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <RefreshCw className="h-6 w-6 animate-spin text-primary" />
    </div>
  );
}

function LoginScreen({
  busy,
  error,
  password,
  setPassword,
  onSubmit,
}: {
  busy: boolean;
  error: string;
  password: string;
  setPassword: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div>
            <h1 className="text-lg font-semibold">JobRadarAI</h1>
            <p className="text-sm text-muted-foreground">Acces prive</p>
          </div>
          <ShieldCheck className="h-5 w-5 text-primary" />
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={onSubmit}>
            <Input
              type="password"
              autoComplete="current-password"
              placeholder="Mot de passe"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {error ? <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">{error}</p> : null}
            <Button className="w-full" disabled={busy || !password}>
              {busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              Entrer
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryCards({ summary }: { summary: Summary | null }) {
  const items = [
    { label: "Queue", value: summary?.queue_count ?? 0, icon: BriefcaseBusiness },
    { label: "VIE", value: summary?.vie_queue_count ?? 0, icon: FileText },
    { label: "Apply now", value: summary?.queue_bucket_counts?.apply_now ?? 0, icon: CheckCircle2 },
    { label: "Postule", value: summary?.application_status_counts?.applied ?? 0, icon: MessageSquareText },
    { label: "Liens vus", value: summary?.audit?.link_checked_count ?? 0, icon: ExternalLink },
  ];
  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map((item) => (
        <Card key={item.label}>
          <CardContent className="p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">{item.label}</p>
              <item.icon className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-1 text-2xl font-semibold">{item.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function Pipeline({
  jobs,
  selectedId,
  onSelect,
  onPatch,
}: {
  jobs: JobItem[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onPatch: (job: JobItem, patch: Partial<JobItem>) => Promise<void>;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
      {statusOptions.map((status) => {
        const allColumnJobs = jobs.filter((job) => job.application_status === status.value);
        const columnJobs = allColumnJobs.slice(0, 28);
        return (
          <Card key={status.value} className="min-w-0">
            <CardHeader className="p-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{status.label}</p>
                <p className="text-xs text-muted-foreground">
                  {columnJobs.length}
                  {allColumnJobs.length > columnJobs.length ? ` / ${allColumnJobs.length}` : ""} visibles
                </p>
              </div>
            </CardHeader>
            <CardContent className="max-h-[760px] space-y-2 overflow-auto p-3 scrollbar-thin">
              {columnJobs.length ? (
                columnJobs.map((job) => (
                  <JobCard
                    key={job.stable_id}
                    job={job}
                    selected={job.stable_id === selectedId}
                    onSelect={onSelect}
                    onPatch={onPatch}
                  />
                ))
              ) : (
                <EmptyState label="Aucune offre dans ce statut." />
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function JobCard({
  job,
  selected,
  onSelect,
  onPatch,
}: {
  job: JobItem;
  selected: boolean;
  onSelect: (id: string) => void;
  onPatch: (job: JobItem, patch: Partial<JobItem>) => Promise<void>;
}) {
  return (
    <article
      className={cn(
        "rounded-md border bg-background p-3 transition hover:border-primary",
        selected && "border-primary ring-1 ring-primary"
      )}
    >
      <button className="block w-full text-left" onClick={() => onSelect(job.stable_id)}>
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="line-clamp-2 text-sm font-semibold">{job.title || "Sans titre"}</p>
            <p className="truncate text-xs text-muted-foreground">{job.company || "Entreprise inconnue"}</p>
          </div>
          <Badge className="shrink-0" variant={bucketVariant(job.queue_bucket)}>
            {bucketLabel(job.queue_bucket)}
          </Badge>
        </div>
        <div className="mt-3 flex flex-wrap gap-1">
          <Badge variant="outline">{scoreLabel(job)}</Badge>
          <Badge variant={checkVariant(job.experience_check)}>{job.experience_check || "xp ?"}</Badge>
          <Badge variant={checkVariant(job.remote_location_validity || job.remote_check)}>
            {job.remote_location_validity || job.remote_check || "remote ?"}
          </Badge>
        </div>
      </button>
      <Select
        aria-label={`Changer le statut de ${job.title || "cette offre"}`}
        className="mt-3 h-8"
        value={job.application_status}
        onChange={(event) => void onPatch(job, { application_status: event.target.value as ApplicationStatus })}
      >
        {statusOptions.map((status) => (
          <option key={status.value} value={status.value}>
            {status.label}
          </option>
        ))}
      </Select>
    </article>
  );
}

function Queue({ jobs, selectedId, onSelect }: { jobs: JobItem[]; selectedId?: string; onSelect: (id: string) => void }) {
  return (
    <Card>
      <CardHeader>
        <div>
          <p className="font-semibold">Queue</p>
          <p className="text-sm text-muted-foreground">{jobs.length} offres filtrees</p>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {jobs.length ? (
          <div className="divide-y">
            {jobs.map((job) => (
              <button
                key={job.stable_id}
                className={cn(
                  "grid w-full gap-2 px-4 py-3 text-left hover:bg-muted/70 md:grid-cols-[minmax(0,1fr)_120px_130px_120px]",
                  selectedId === job.stable_id && "bg-secondary/60"
                )}
                onClick={() => onSelect(job.stable_id)}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{job.title}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {job.company} · {job.market} · {job.source}
                  </p>
                </div>
                <Badge className="shrink-0" variant={bucketVariant(job.queue_bucket)}>
                  {bucketLabel(job.queue_bucket)}
                </Badge>
                <Badge variant={checkVariant(job.experience_check)}>{job.experience_check || "experience ?"}</Badge>
                <p className="text-sm font-medium">{scoreLabel(job)}</p>
              </button>
            ))}
          </div>
        ) : (
          <div className="p-4">
            <EmptyState label="Aucune offre ne correspond aux filtres." />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DetailPanel({
  job,
  onPatch,
  onAddEvent,
  onCopyText,
}: {
  job?: JobItem;
  onPatch: (job: JobItem, patch: Partial<JobItem>) => Promise<void>;
  onAddEvent: (job: JobItem, note: string) => Promise<void>;
  onCopyText: (text: string, label?: string) => Promise<void>;
}) {
  const [notes, setNotes] = useState("");
  const [eventNote, setEventNote] = useState("");
  const [applicationUrl, setApplicationUrl] = useState("");
  const [contactUrl, setContactUrl] = useState("");
  const [customCv, setCustomCv] = useState("");

  useEffect(() => {
    setNotes(job?.notes || "");
    setEventNote("");
    setApplicationUrl(job?.application_url || "");
    setContactUrl(job?.contact_url || "");
    setCustomCv(job?.custom_cv || "");
  }, [job?.stable_id, job?.notes, job?.application_url, job?.contact_url, job?.custom_cv]);

  if (!job) {
    return (
      <aside className="xl:sticky xl:top-[78px] xl:self-start">
        <Card>
          <CardContent className="text-sm text-muted-foreground">Aucune offre dans les filtres actuels.</CardContent>
        </Card>
      </aside>
    );
  }

  const angle = job.application_angle || job.last_application_angle || "";
  return (
    <aside className="space-y-4 lg:col-span-2 xl:col-span-1 xl:sticky xl:top-[78px] xl:max-h-[calc(100vh-96px)] xl:overflow-auto xl:self-start xl:pr-1 scrollbar-thin">
      <Card>
        <CardHeader>
          <div className="min-w-0">
            <h2 className="line-clamp-2 text-base font-semibold">{job.title}</h2>
            <p className="truncate text-sm text-muted-foreground">
              {job.company} · {job.market} · {job.location || job.source}
            </p>
          </div>
          <Badge className="shrink-0" variant={bucketVariant(job.queue_bucket)}>
            {bucketLabel(job.queue_bucket)}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <Signal label="Score" value={scoreLabel(job)} />
            <Signal label="Lien" value={job.last_link_status || "not_checked"} />
            <Signal label="Niveau" value={job.last_level_fit || "unknown"} />
            <Signal label="Experience" value={job.experience_check || "unknown"} />
            <Signal label="Annees req." value={job.required_years == null ? "unknown" : String(job.required_years)} />
            <Signal label="Langue" value={job.language_check || "unknown"} />
            <Signal label="Remote" value={job.remote_location_validity || job.remote_check || "unknown"} />
            <Signal label="Start" value={job.start_date_check || "unknown"} />
            <Signal label="Deadline" value={job.deadline || "unknown"} />
            <Signal label="Salaire" value={salaryLabel(job)} />
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <Select
              aria-label="Statut de candidature"
              value={job.application_status}
              onChange={(event) => void onPatch(job, { application_status: event.target.value as ApplicationStatus })}
            >
              {statusOptions.map((status) => (
                <option key={status.value} value={status.value}>
                  {status.label}
                </option>
              ))}
            </Select>
            <Select aria-label="Fit utilisateur" value={job.fit_status} onChange={(event) => void onPatch(job, { fit_status: event.target.value as FitStatus })}>
              {fitOptions.map((status) => (
                <option key={status.value} value={status.value}>
                  {status.label}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Priorite utilisateur"
              value={job.user_priority}
              onChange={(event) => void onPatch(job, { user_priority: event.target.value as UserPriority })}
            >
              {priorityOptions.map((priority) => (
                <option key={priority.value} value={priority.value}>
                  {priority.label}
                </option>
              ))}
            </Select>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              aria-label="Date de prochaine action"
              type="date"
              value={job.next_action_at}
              onChange={(event) => void onPatch(job, { next_action_at: event.target.value })}
            />
            <Input
              aria-label="Nom du contact"
              placeholder="Contact"
              value={job.contact_name}
              onChange={(event) => void onPatch(job, { contact_name: event.target.value })}
            />
          </div>

          <div className="space-y-2">
            <Input
              aria-label="URL de candidature"
              placeholder="URL de candidature"
              value={applicationUrl}
              onChange={(event) => setApplicationUrl(event.target.value)}
              onBlur={() => void onPatch(job, { application_url: applicationUrl })}
            />
            <Input
              aria-label="URL du contact ou profil RH"
              placeholder="URL contact / profil RH"
              value={contactUrl}
              onChange={(event) => setContactUrl(event.target.value)}
              onBlur={() => void onPatch(job, { contact_url: contactUrl })}
            />
            <div className="grid gap-2 sm:grid-cols-2">
              <Input
                aria-label="Dernier contact"
                type="date"
                value={job.last_contacted_at}
                onChange={(event) => void onPatch(job, { last_contacted_at: event.target.value })}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={!job.contact_url}
                onClick={() => openLink(job.contact_url)}
              >
                <ExternalLink className="h-4 w-4" />
                Contact
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="default" size="sm" disabled={!(job.application_url || job.url)} onClick={() => openLink(job.application_url || job.url)}>
              <ExternalLink className="h-4 w-4" />
              Candidater
            </Button>
            <Button variant="outline" size="sm" disabled={!(job.recruiter_message || angle)} onClick={() => void onCopyText(job.recruiter_message || angle, "Message RH")}>
              <Copy className="h-4 w-4" />
              Copier message
            </Button>
            {job.url ? (
              <Button variant="outline" size="icon" aria-label="Ouvrir l'offre" onClick={() => openLink(job.url)}>
                <ExternalLink className="h-4 w-4" />
              </Button>
            ) : null}
          </div>

          {angle ? (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Angle</p>
              <p className="rounded-md border bg-muted/40 p-3 text-sm">{angle}</p>
            </div>
          ) : null}

          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">Message RH</p>
            <Textarea readOnly value={job.recruiter_message || ""} className="min-h-40" />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">CV / variante a utiliser</p>
              <Button size="sm" variant="outline" onClick={() => void onPatch(job, { custom_cv: customCv })}>
                Sauver
              </Button>
            </div>
            <Textarea value={customCv} onChange={(event) => setCustomCv(event.target.value)} placeholder="Ex: CV data/AI, CV research, ajustements a faire avant candidature..." />
          </div>

          {job.experience_evidence ? (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Evidence experience</p>
              <p className="rounded-md border bg-muted/40 p-3 text-sm">{job.experience_evidence}</p>
            </div>
          ) : null}

          <div>
            <div className="mb-1 flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">Notes</p>
              <Button size="sm" variant="outline" onClick={() => void onPatch(job, { notes })}>
                Sauver
              </Button>
            </div>
            <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <CalendarClock className="h-4 w-4" />
            Timeline
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea placeholder="Nouvelle note" value={eventNote} onChange={(event) => setEventNote(event.target.value)} />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              void onAddEvent(job, eventNote).then(() => setEventNote(""));
            }}
          >
            Ajouter
          </Button>
          <div className="space-y-2">
            {(job.events || [])
              .slice()
              .reverse()
              .map((event, index) => (
                <div key={`${event.at}-${index}`} className="rounded-md border p-2">
                  <p className="text-xs font-medium text-muted-foreground">{formatDate(event.at)}</p>
                  <p className="text-sm">{event.note || event.type}</p>
                </div>
              ))}
          </div>
        </CardContent>
      </Card>
    </aside>
  );
}

function Signal({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border bg-background p-2">
      <p className="truncate text-[11px] font-medium text-muted-foreground">{label}</p>
      <p className="truncate text-sm">{value}</p>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function NoticeToast({ notice }: { notice: Notice | null }) {
  if (!notice) return null;
  const Icon = notice.type === "success" ? CheckCircle2 : AlertTriangle;
  return (
    <div
      role="status"
      className={cn(
        "fixed bottom-4 right-4 z-50 flex max-w-[calc(100vw-2rem)] items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm shadow-lg",
        notice.type === "success" ? "border-emerald-200 text-emerald-800" : "border-destructive/30 text-destructive"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="truncate">{notice.message}</span>
    </div>
  );
}

function CvPanel({ summary }: { summary: Summary | null }) {
  const cv = summary?.cv;
  return (
    <Card>
      <CardHeader>
        <div>
          <p className="font-semibold">CV</p>
          <p className="text-sm text-muted-foreground">{cv?.pdf_available ? "PDF disponible" : "Source TeX disponible"}</p>
        </div>
        {cv?.tex_url ? (
          <Button variant="outline" size="sm" onClick={() => openLink(cv.tex_url)}>
            <FileText className="h-4 w-4" />
            TeX
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {cv?.pdf_available && cv.pdf_url ? (
          <iframe title="CV" src={cv.pdf_url} className="h-[78vh] w-full rounded-md border bg-white" />
        ) : (
          <pre className="max-h-[78vh] overflow-auto rounded-md border bg-muted/40 p-3 text-xs">{cv?.tex_excerpt || "Aucun CV monte."}</pre>
        )}
      </CardContent>
    </Card>
  );
}

function scoreLabel(job: JobItem) {
  const score = job.last_combined_score ?? job.score;
  return typeof score === "number" ? Math.round(score).toString() : "score ?";
}

function salaryLabel(job: JobItem) {
  if (typeof job.salary_normalized_annual_eur === "number") {
    return `${Math.round(job.salary_normalized_annual_eur / 1000)}k EUR`;
  }
  return job.salary_check || job.last_salary_check || "unknown";
}

function bucketVariant(bucket?: string) {
  if (bucket === "apply_now") return "success";
  if (bucket === "shortlist") return "secondary";
  if (bucket === "high_score") return "warning";
  return "muted";
}

function bucketLabel(bucket?: string) {
  if (bucket === "apply_now") return "Apply now";
  if (bucket === "shortlist") return "Shortlist";
  if (bucket === "high_score") return "High score";
  if (bucket === "maybe") return "Maybe";
  return "Queue";
}

function checkVariant(value?: string) {
  if (!value) return "muted";
  if (["meets", "compatible", "english_ok", "junior_ok", "ok"].includes(value)) return "success";
  if (["too_senior", "too_soon", "below_min", "blocked", "invalid"].includes(value)) return "warning";
  return "outline";
}

function openLink(url?: string) {
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

function formatDate(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

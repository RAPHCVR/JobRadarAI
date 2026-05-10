export type ApplicationStatus =
  | "to_review"
  | "interested"
  | "applied"
  | "follow_up"
  | "interview"
  | "offer"
  | "rejected"
  | "archived";

export type FitStatus = "unknown" | "strong" | "ok" | "stretch" | "low" | "blocked";
export type UserPriority = "low" | "normal" | "high" | "urgent";

export type JobEvent = {
  type: string;
  note: string;
  at: string;
};

export type JobItem = {
  stable_id: string;
  queue_bucket?: string;
  title?: string;
  company?: string;
  url?: string;
  market?: string;
  location?: string;
  source?: string;
  presence_status?: string;
  last_link_status?: string;
  last_combined_score?: number;
  score?: number;
  last_level_fit?: string;
  start_date_check?: string;
  salary_check?: string;
  last_salary_check?: string;
  remote_check?: string;
  language_check?: string;
  remote_location_validity?: string;
  required_years?: number | null;
  experience_check?: string;
  experience_evidence?: string;
  salary_normalized_annual_eur?: number | null;
  deadline?: string;
  application_angle?: string;
  last_application_angle?: string;
  recruiter_message?: string;
  application_status: ApplicationStatus;
  fit_status: FitStatus;
  user_priority: UserPriority;
  notes: string;
  next_action_at: string;
  contact_name: string;
  contact_url: string;
  application_url: string;
  custom_cv: string;
  last_contacted_at: string;
  state_updated_at?: string;
  events: JobEvent[];
};

export type Summary = {
  run_name?: string;
  current_jobs?: number;
  known_jobs?: number;
  new_jobs?: number;
  missing_this_run?: number;
  queue_count?: number;
  vie_queue_count?: number;
  queue_bucket_counts?: Record<string, number>;
  application_status_counts?: Record<string, number>;
  link_status_counts?: Record<string, number>;
  market_counts?: Record<string, number>;
  audit?: {
    sources_ok?: number;
    sources_skipped?: number;
    source_errors?: number;
    llm_count?: number;
    link_checked_count?: number;
  };
  cv?: {
    pdf_available?: boolean;
    pdf_url?: string;
    tex_available?: boolean;
    tex_url?: string;
    tex_excerpt?: string;
    pdf_updated_at?: string;
    tex_updated_at?: string;
  };
  links?: Record<string, string>;
};

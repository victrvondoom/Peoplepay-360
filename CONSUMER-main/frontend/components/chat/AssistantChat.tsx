"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot, Send, Mic, MicOff, Sparkles, Loader2, AlertCircle, Command, Trash2, RotateCcw, Zap,
} from "lucide-react";
import {
  classifyQuery, runMultiDomainCase, type DomainCandidate, type Citation, type MultiDomainCaseResponse, type AgentBreakdown,
} from "@/lib/api-client";
import { ESTIMATED_STAGES } from "./pipeline";
import { ReasoningLanes } from "./ReasoningLanes";
import { CitationConstellation } from "./CitationConstellation";
import { domainTheme } from "./domain-theme";
import { markdownComponents } from "./markdown-components";
import { AgentReasoningTrace } from "./AgentReasoningTrace";
import { PipelineSidebar } from "./PipelineSidebar";

interface DomainAnswer {
  domain: string;
  route: string;
  report: string | null;
  trace: string[];
  breakdown: AgentBreakdown;
  confidence: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  domains?: string[];
  citations?: Citation[];
  perDomainTraces?: Record<string, string[]>;
  perDomainAnswers?: DomainAnswer[];
  error?: string;
}

// Bumped to v2 when DomainAnswer gained required trace/breakdown/confidence
// fields -- old v1 history in a returning user's browser predates those
// fields entirely (not just empty), so loading it would crash components
// that read them. A new key just leaves the old entry orphaned in
// localStorage rather than needing a migration.
const STORAGE_KEY = "proxy:assistant-chat-history-v2";

function loadHistory(): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(messages: ChatMessage[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-50)));
  } catch {
    // storage full or unavailable -- conversation still works, just won't persist
  }
}

function useSpeechRecognition(onResult: (text: string) => void) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    const SpeechRecognition = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    setSupported(true);
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = (event: any) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) onResult(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
  }, [onResult]);

  function toggle() {
    if (!recognitionRef.current) return;
    if (listening) {
      recognitionRef.current.stop();
      setListening(false);
    } else {
      recognitionRef.current.start();
      setListening(true);
    }
  }

  return { supported, listening, toggle };
}

export function AssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [livePreview, setLivePreview] = useState<DomainCandidate[]>([]);
  const [processing, setProcessing] = useState(false);
  const [processingDomains, setProcessingDomains] = useState<string[]>([]);
  const [filledCount, setFilledCount] = useState(0);
  const [processingElapsedMs, setProcessingElapsedMs] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stageTimerRef = useRef<number | null>(null);

  // ESTIMATED_STAGES finishes animating in ~10s, but a real multi-agent run
  // (several sequential LLM calls per domain) can take 30-120+s -- without a
  // ticking clock the UI looks frozen for the rest of that time.
  useEffect(() => {
    if (!processing) {
      setProcessingElapsedMs(0);
      return;
    }
    const start = performance.now();
    const timer = window.setInterval(() => setProcessingElapsedMs(Math.round(performance.now() - start)), 200);
    return () => window.clearInterval(timer);
  }, [processing]);

  useEffect(() => setMessages(loadHistory()), []);
  useEffect(() => { if (messages.length) saveHistory(messages); }, [messages]);

  // Cross-page handoff from Cross-Domain Search's "Ask the AI Assistant"
  // action (?q=...) -- pre-fills but doesn't auto-send, so the user reviews
  // before it runs a real (slow, LLM-backed) multi-agent query.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q) {
      setInput(q);
      window.setTimeout(() => textareaRef.current?.focus(), 100);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, filledCount]);

  useEffect(() => {
    if (input.trim().length < 12) {
      setLivePreview([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        setLivePreview((await classifyQuery(input)).candidates);
      } catch {
        setLivePreview([]);
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    function onKeydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        textareaRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  const { supported: voiceSupported, listening, toggle: toggleVoice } = useSpeechRecognition((text) => {
    setInput((current) => (current ? `${current} ${text}` : text));
  });

  async function send() {
    const text = input.trim();
    if (!text || processing) return;

    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: text, timestamp: Date.now() }]);
    const caseId = crypto.randomUUID();
    setInput("");
    setLivePreview([]);
    setProcessing(true);
    setFilledCount(0);
    setProcessingDomains(livePreview.length ? livePreview.map((c) => c.domain) : []);

    let stageIndex = 0;
    stageTimerRef.current = window.setInterval(() => {
      stageIndex = Math.min(stageIndex + 1, ESTIMATED_STAGES.length);
      setFilledCount(stageIndex);
    }, 1300);

    try {
      const response: MultiDomainCaseResponse = await runMultiDomainCase(caseId, text);
      const perDomainTraces: Record<string, string[]> = {};
      const perDomainAnswers: DomainAnswer[] = [];
      Object.entries(response.per_domain_results).forEach(([domain, result]) => {
        perDomainTraces[domain] = result.agent_trace ?? [];
        perDomainAnswers.push({ domain, route: result.route, report: result.final_report, trace: result.agent_trace ?? [], breakdown: result.agent_breakdown, confidence: result.confidence });
      });
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          timestamp: Date.now(),
          domains: response.domains_analyzed,
          citations: response.combined_citations,
          perDomainTraces,
          perDomainAnswers,
        },
      ]);
    } catch (err) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          timestamp: Date.now(),
          error: err instanceof Error ? err.message : "Something went wrong reaching the multi-agent backend.",
        },
      ]);
    } finally {
      if (stageTimerRef.current) window.clearInterval(stageTimerRef.current);
      setProcessing(false);
      setProcessingDomains([]);
      setFilledCount(0);
    }
  }

  function retryLast() {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setMessages((current) => (current[current.length - 1]?.role === "assistant" ? current.slice(0, -1) : current));
    setInput(lastUser.content);
    window.setTimeout(() => send(), 0);
  }

  function clearConversation() {
    setMessages([]);
    window.localStorage.removeItem(STORAGE_KEY);
  }

  // The sidebar always reflects the most current turn: while typing/running
  // it's the live classification + in-flight trace; once a message lands,
  // it switches to that message's real first-domain trace and breakdown.
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant" && !m.error);
  const primaryAnswer = lastAssistant?.perDomainAnswers?.[0];
  const sidebarCandidates = processing
    ? (processingDomains.length ? processingDomains : livePreview.map((c) => c.domain)).map((d) => ({ domain: d }))
    : livePreview.length > 0
      ? livePreview.map((c) => ({ domain: c.domain, confidence: c.confidence }))
      : (lastAssistant?.domains ?? []).map((d) => ({
          domain: d,
          confidence: lastAssistant?.perDomainAnswers?.find((a) => a.domain === d)?.confidence,
        }));
  const sidebarTrace = processing ? [] : primaryAnswer?.trace ?? [];

  return (
    <div className="flex min-h-0 flex-1 gap-4">
      <div className="flex min-h-0 flex-1 flex-col rounded-2xl border border-white/10 bg-glass backdrop-blur-2xl">
        <ChatHeader onClear={clearConversation} busy={processing} />

        {/* This is the only scrollable region -- the header above and the
            Composer below are outside this div, in the same flex-col, so
            they hold a fixed position regardless of how much content
            streams in here. min-h-0 is required: without it a flex child
            refuses to shrink below its content size, and overflow-y-auto
            never actually kicks in, letting this div (and the whole page)
            grow taller with every generated answer instead. */}
        <div ref={scrollRef} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-8">
          {messages.length === 0 && !processing && <BootSequence onPick={setInput} />}

          {messages.map((message) =>
            message.role === "user" ? (
              <UserPrompt key={message.id} text={message.content} />
            ) : (
              <IntelligenceCard key={message.id} message={message} onRetry={message.error ? retryLast : undefined} />
            )
          )}

          {processing && (
            <IntelligenceCard
              message={{ id: "processing", role: "assistant", content: "", timestamp: Date.now() }}
              processing
              processingDomains={processingDomains.length ? processingDomains : ["health_insurance"]}
              filledCount={filledCount}
              elapsedMs={processingElapsedMs}
            />
          )}
        </div>

        <Composer
          input={input}
          setInput={setInput}
          onSend={send}
          processing={processing}
          textareaRef={textareaRef}
          voiceSupported={voiceSupported}
          listening={listening}
          onToggleVoice={toggleVoice}
          livePreview={livePreview}
        />
      </div>

      {/* No overflow-y-auto here: the sidebar's natural content height
          (Detected + Agent Pipeline) comfortably fits without scrolling in
          normal use, and forcing it into the row's clamped height with
          scrollbars now hidden globally meant content got silently clipped
          with no visible affordance that more existed below. */}
      <div className="hidden self-start py-4 xl:block">
        <PipelineSidebar
          candidates={sidebarCandidates}
          primaryDomain={primaryAnswer?.domain}
          primaryRoute={primaryAnswer?.route}
          trace={sidebarTrace}
          processing={processing}
        />
      </div>
    </div>
  );
}

function ChatHeader({ onClear, busy }: { onClear: () => void; busy: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 sm:px-6">
      <div className="flex items-center gap-3">
        <div className="relative grid size-9 place-items-center rounded-xl border border-cyan-300/30 bg-cyan-300/10">
          <Sparkles className="size-4 text-cyan-200" />
          {busy && <span className="absolute -right-1 -top-1 size-2.5 animate-ping rounded-full bg-cyan-300" />}
          {busy && <span className="absolute -right-1 -top-1 size-2.5 rounded-full bg-cyan-300" />}
        </div>
        <div>
          <p className="text-sm font-semibold">PROXY Neural Assistant</p>
          <p className="text-[11px] text-proxy-tertiary">8 domains &middot; parallel multi-agent reasoning &middot; every claim cited</p>
        </div>
      </div>
      <button
        onClick={onClear}
        className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-proxy-muted hover:border-red-300/30 hover:text-red-100"
      >
        <Trash2 className="size-3.5" /> Clear
      </button>
    </div>
  );
}

function BootSequence({ onPick }: { onPick: (prompt: string) => void }) {
  const lines = [
    "Domain Router: 8 domains online",
    "Evidence Scoring Engine: ready",
    "Citation Engine: ready",
    "Multi-agent workflow: ready to reason",
  ];
  const suggestions = [
    "My flight was cancelled and my travel insurance rejected the claim.",
    "My builder delayed possession of my flat by 18 months under RERA.",
    "What are the symptoms of dengue fever and when should I see a doctor?",
    "My credit card was charged twice for the same transaction.",
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 py-10">
      <div className="text-center">
        <div className="mx-auto mb-4 grid size-16 place-items-center rounded-2xl border border-cyan-300/25 bg-cyan-300/10 shadow-glow-cyan">
          <Bot className="size-8 text-cyan-200" />
        </div>
        <div className="font-mono text-[11px] text-proxy-tertiary">
          {lines.map((line, index) => (
            <p
              key={line}
              className="opacity-0"
              style={{ animation: `fadeIn .4s ease forwards`, animationDelay: `${index * 220}ms` }}
            >
              <span className="text-green-300">&#10003;</span> {line}
            </p>
          ))}
        </div>
        <p className="mt-4 text-lg font-semibold">Ask across any domain -- or several at once</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-proxy-muted">
          One question can span multiple domains. Watch PROXY classify, reason, and cite each one in parallel.
        </p>
      </div>
      <div className="grid w-full max-w-lg gap-2 sm:grid-cols-2">
        {suggestions.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onPick(prompt)}
            className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-left text-xs text-proxy-muted transition-colors hover:border-cyan-300/30 hover:text-proxy-text"
          >
            {prompt}
          </button>
        ))}
      </div>
      <style jsx>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(2px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

function UserPrompt({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[70%] rounded-2xl rounded-tr-sm border border-purple-300/20 bg-purple-300/10 px-4 py-2.5 text-sm text-proxy-text">
        {text}
      </div>
    </div>
  );
}

const STILL_REASONING_PHRASES = [
  "Reasoning across domains...",
  "Cross-checking clauses and regulations...",
  "Scoring evidence and building strategy...",
  "Complex multi-domain queries can take up to two minutes -- still working.",
];

function IntelligenceCard({
  message, processing, processingDomains, filledCount, elapsedMs, onRetry,
}: {
  message: ChatMessage;
  processing?: boolean;
  processingDomains?: string[];
  filledCount?: number;
  elapsedMs?: number;
  onRetry?: () => void;
}) {
  const domains = processing ? (processingDomains ?? []) : message.domains ?? [];
  const lanes = domains.map((domain) => ({ domain, trace: message.perDomainTraces?.[domain] }));
  const elapsedSeconds = (elapsedMs ?? 0) / 1000;
  const reasoningLabel = STILL_REASONING_PHRASES[Math.min(Math.floor(elapsedSeconds / 15), STILL_REASONING_PHRASES.length - 1)];

  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4 sm:p-5">
      <div className="mb-3 flex items-center gap-2">
        <div className="grid size-7 place-items-center rounded-lg border border-cyan-300/25 bg-cyan-300/10">
          {processing ? <Loader2 className="size-3.5 animate-spin text-cyan-200" /> : <Zap className="size-3.5 text-cyan-200" />}
        </div>
        <p className="text-xs font-medium text-proxy-muted">
          {processing ? reasoningLabel : "PROXY"}
        </p>
        {processing && (
          <span className="ml-auto font-mono text-[10px] text-cyan-200">{elapsedSeconds.toFixed(1)}s</span>
        )}
        {!processing && domains.length > 0 && (
          <div className="ml-auto flex flex-wrap gap-1.5">
            {domains.map((domain) => {
              const theme = domainTheme(domain);
              return (
                <span
                  key={domain}
                  className="rounded-full border px-2 py-0.5 text-[10px]"
                  style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a`, color: theme.color }}
                >
                  {theme.label}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {lanes.length > 0 && (
        <div className="mb-4">
          <ReasoningLanes lanes={lanes} processing={Boolean(processing)} filledCount={filledCount ?? lanes[0]?.trace?.length ?? 0} />
        </div>
      )}

      {message.error ? (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-red-300/25 bg-red-300/10 px-4 py-3 text-sm text-red-100">
          <span className="flex items-center gap-2"><AlertCircle className="size-4 shrink-0" /> {message.error}</span>
          {onRetry && (
            <button onClick={onRetry} className="inline-flex shrink-0 items-center gap-1 text-xs text-red-200 hover:text-red-100">
              <RotateCcw className="size-3" /> Retry
            </button>
          )}
        </div>
      ) : (
        message.perDomainAnswers && (
          <div className="space-y-3">
            {message.perDomainAnswers.map((answer) => (
              <DomainAnswerSection key={answer.domain} answer={answer} />
            ))}
          </div>
        )
      )}

      {message.citations && message.citations.length > 0 && (
        <div className="mt-4 border-t border-white/5 pt-4">
          <CitationConstellation citations={message.citations} />
        </div>
      )}
    </div>
  );
}

function DomainAnswerSection({ answer }: { answer: DomainAnswer }) {
  const theme = domainTheme(answer.domain);
  const [expanded, setExpanded] = useState(true);
  if (!answer.report) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-white/5" style={{ borderLeftColor: theme.color, borderLeftWidth: 3 }}>
      <button
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-center justify-between bg-white/[0.02] px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 text-xs font-medium" style={{ color: theme.color }}>
          {theme.label}
          <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px] text-proxy-tertiary">{answer.route}</span>
        </span>
        <span className="text-[10px] text-proxy-tertiary">{expanded ? "Collapse" : "Expand"}</span>
      </button>
      {expanded && (
        <div className="px-4 py-3">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {answer.report}
          </ReactMarkdown>
          <DraftedDocuments negotiation={answer.breakdown.negotiation} color={theme.color} />
          <AgentReasoningTrace trace={answer.trace} breakdown={answer.breakdown} />
        </div>
      )}
    </div>
  );
}

// The negotiation agent already drafts these on every run -- the
// synthesized report now points to them ("the appeal letter is drafted
// below") instead of asking "would you like me to draft this?", since this
// chat has no conversation continuity between messages. That reference is
// only true if they're actually rendered somewhere, which they previously
// weren't: the agent trace above only ever showed step badges, never the
// document text itself.
function DraftedDocuments({ negotiation, color }: { negotiation?: AgentBreakdown["negotiation"]; color: string }) {
  if (!negotiation) return null;
  const docs: Array<[string, string | undefined]> = [
    ["Appeal / dispute letter", negotiation.appeal_letter],
    ["Complaint email", negotiation.complaint_email],
    ["Escalation note", negotiation.escalation_note],
    ["Consumer complaint", negotiation.consumer_complaint],
  ];
  const available = docs.filter(([, v]) => v && v.trim()) as Array<[string, string]>;
  if (available.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      <p className="text-[10px] font-medium uppercase tracking-wide text-proxy-tertiary">Drafted documents (ready to review and send)</p>
      {available.map(([label, content]) => (
        <details key={label} className="rounded-lg border border-white/10 bg-black/20 p-2.5">
          <summary className="cursor-pointer text-xs font-medium" style={{ color }}>{label}</summary>
          <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-proxy-muted">{content}</p>
        </details>
      ))}
    </div>
  );
}

function Composer({
  input, setInput, onSend, processing, textareaRef, voiceSupported, listening, onToggleVoice, livePreview,
}: {
  input: string;
  setInput: (value: string) => void;
  onSend: () => void;
  processing: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  voiceSupported: boolean;
  listening: boolean;
  onToggleVoice: () => void;
  livePreview: DomainCandidate[];
}) {
  return (
    <div className="border-t border-white/10 p-3 sm:p-4">
      {livePreview.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5 px-1">
          <span className="text-[10px] uppercase tracking-wide text-proxy-tertiary">Detected:</span>
          {livePreview.map((candidate) => {
            const theme = domainTheme(candidate.domain);
            return (
              <span
                key={candidate.domain}
                className="rounded-full border px-2 py-0.5 text-[10px]"
                style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a`, color: theme.color }}
              >
                {theme.label}
              </span>
            );
          })}
        </div>
      )}
      <div className="composer-glow flex items-end gap-2 rounded-2xl p-[1.5px]">
        <div className="flex w-full items-end gap-2 rounded-2xl bg-[#07080b] p-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSend();
              }
            }}
            placeholder="Ask about any domain -- or several at once... (Ctrl/Cmd+K to focus)"
            rows={1}
            className="max-h-32 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-proxy-text outline-none placeholder:text-proxy-tertiary"
          />
          {voiceSupported && (
            <button
              onClick={onToggleVoice}
              className={`relative grid size-9 shrink-0 place-items-center rounded-full border transition-colors ${
                listening ? "border-red-300/50 bg-red-300/10 text-red-200" : "border-white/10 text-proxy-muted hover:border-cyan-300/30"
              }`}
              title={listening ? "Stop listening" : "Voice input"}
            >
              {listening && <span className="absolute inset-0 animate-ping rounded-full bg-red-400/20" />}
              {listening ? <MicOff className="size-4" /> : <Mic className="size-4" />}
            </button>
          )}
          <button
            onClick={onSend}
            disabled={processing || !input.trim()}
            className="orb-send grid size-10 shrink-0 place-items-center rounded-full text-black transition-transform disabled:cursor-not-allowed disabled:opacity-40 enabled:hover:scale-105"
          >
            {processing ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </button>
        </div>
      </div>
      <div className="mt-1.5 flex items-center gap-1 px-1 text-[10px] text-proxy-tertiary">
        <Command className="size-3" /> K to focus &middot; Enter to send &middot; Shift+Enter for new line
      </div>

      <style jsx>{`
        .composer-glow {
          background: linear-gradient(120deg, rgba(0, 229, 255, 0.5), rgba(155, 92, 255, 0.5), rgba(0, 229, 255, 0.5));
          background-size: 200% 200%;
          animation: glowShift 6s ease infinite;
        }
        @keyframes glowShift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        .orb-send {
          background: radial-gradient(circle at 30% 30%, #5cf5ff, #00b8d9 55%, #6a3df0);
          box-shadow: 0 0 18px rgba(0, 229, 255, 0.45);
        }
      `}</style>
    </div>
  );
}

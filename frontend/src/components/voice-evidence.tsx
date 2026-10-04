"use client";

import { useEffect, useRef, useState } from "react";
import { AudioLines, ChevronDown, Loader2, RotateCw } from "lucide-react";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, clearSession, errorMessage, readSession } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { CustomerVoice, VoiceSample, VoiceTranscription } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { formatDateTime } from "@/lib/utils";

function timestamp(seconds: number) {
  const value = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

function VoiceRecording({ sample, speechAvailable }: { sample: VoiceSample; speechAvailable: boolean }) {
  const { session } = useAuth();
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [job, setJob] = useState<VoiceTranscription | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const audioRequest = useRef<AbortController | null>(null);
  const actionRequest = useRef<AbortController | null>(null);
  const blobUrl = useRef<string | null>(null);
  const path = `/voice/${encodeURIComponent(sample.voice_sample_id)}`;

  useEffect(() => {
    const controller = new AbortController();
    setJob(null);
    setJobError(null);
    setStatusLoading(true);
    api<VoiceTranscription>(`${path}/transcription`, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setJob(result);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setJobError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setStatusLoading(false);
      });
    return () => controller.abort();
  }, [path, session?.token]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status) || actionLoading || jobError) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api<VoiceTranscription>(`${path}/transcription`, { signal: controller.signal })
        .then((result) => {
          if (!controller.signal.aborted) setJob(result);
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) setJobError(errorMessage(error));
        });
    }, 2000);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [job, path, actionLoading, jobError, session?.token]);

  useEffect(() => {
    setAudioUrl(null);
    setAudioLoading(false);
    setAudioError(null);
    setActionLoading(false);
    return () => {
      audioRequest.current?.abort();
      actionRequest.current?.abort();
      if (blobUrl.current) URL.revokeObjectURL(blobUrl.current);
      blobUrl.current = null;
    };
  }, [session?.token, path]);

  async function loadAudio() {
    if (audioLoading || !sample.audio_available) return;
    const controller = new AbortController();
    audioRequest.current?.abort();
    audioRequest.current = controller;
    setAudioLoading(true);
    setAudioError(null);
    try {
      const current = readSession();
      if (!current) throw new ApiError("Please sign in to listen to this recording.", 401);
      const response = await fetch(`/api${path}/audio`, {
        headers: { Authorization: `Bearer ${current.token}`, Accept: "audio/wav" },
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 401) {
          clearSession();
          window.dispatchEvent(new Event("session-expired"));
        }
        throw new ApiError(
          response.status === 401 ? "Your session has ended. Please sign in again."
            : response.status === 403 ? "You do not have access to this recording."
              : response.status === 404 ? "This recording is not available locally."
                : "The recording could not be loaded. Please try again.",
          response.status,
        );
      }
      const audio = await response.blob();
      if (controller.signal.aborted) return;
      if (!audio.size) throw new Error("The server returned an empty recording.");
      if (blobUrl.current) URL.revokeObjectURL(blobUrl.current);
      blobUrl.current = URL.createObjectURL(audio);
      setAudioUrl(blobUrl.current);
    } catch (error) {
      if (!controller.signal.aborted) setAudioError(errorMessage(error));
    } finally {
      if (!controller.signal.aborted) setAudioLoading(false);
    }
  }

  async function updateTranscription(start: boolean) {
    if (actionLoading) return;
    const controller = new AbortController();
    actionRequest.current?.abort();
    actionRequest.current = controller;
    setActionLoading(true);
    setJobError(null);
    try {
      const result = await api<VoiceTranscription>(`${path}/${start ? "transcribe" : "transcription"}`, {
        method: start ? "POST" : "GET",
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setJob(result);
    } catch (error) {
      if (!controller.signal.aborted) setJobError(errorMessage(error));
    } finally {
      if (!controller.signal.aborted) setActionLoading(false);
    }
  }

  const processing = job?.status === "queued" || job?.status === "running";
  const transcript = job?.status === "completed" ? job.transcript : undefined;
  const cues = Object.entries(transcript?.features ?? {}).filter(([, value]) => value > 0);

  return (
    <section aria-label={`Recording ${sample.voice_sample_id}`} className="space-y-4 rounded-lg border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-mono text-sm font-medium">{sample.voice_sample_id}</h3>
          <p className="text-muted-foreground mt-1 text-xs">
            {formatDateTime(sample.call_start_ts)} · {sample.language || "Language not recorded"} · {timestamp(sample.duration_sec)}
          </p>
          <p className="text-muted-foreground mt-1 text-xs">Case {sample.case_id} · source transcript {sample.transcript_id}</p>
        </div>
        <Badge variant="outline">Synthetic call audio</Badge>
      </div>

      <div className="space-y-2">
        {audioUrl ? (
          <audio controls preload="metadata" src={audioUrl} aria-label={`Play recording ${sample.voice_sample_id}`} className="w-full"
            onError={() => {
              setAudioError("The browser could not play this WAV recording. Try loading it again.");
              setAudioUrl(null);
            }}>
            Your browser does not support audio playback.
          </audio>
        ) : (
          <Button variant="outline" size="sm" onClick={loadAudio} disabled={!sample.audio_available || audioLoading}>
            {audioLoading ? <Loader2 className="animate-spin" aria-hidden /> : <AudioLines aria-hidden />}
            {audioLoading ? "Loading audio…" : "Load recording"}
          </Button>
        )}
        {!sample.audio_available && <p className="text-muted-foreground text-sm">The WAV file is not installed locally.</p>}
        {audioError && <ErrorState title="Audio unavailable" message={audioError} />}
      </div>

      <div className="space-y-3" aria-live="polite">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => updateTranscription(true)}
            disabled={!speechAvailable || !sample.audio_available || statusLoading || actionLoading || processing || !!transcript}>
            {actionLoading || processing ? <Loader2 className="animate-spin" aria-hidden /> : <AudioLines aria-hidden />}
            {job?.status === "queued" ? "Speech-to-text queued…" : job?.status === "running" ? "Transcribing locally…"
              : actionLoading ? "Requesting…" : job?.status === "failed" ? "Retry speech-to-text" : "Run local speech-to-text"}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => updateTranscription(false)} disabled={statusLoading || actionLoading}>
            <RotateCw aria-hidden /> Refresh status
          </Button>
          {statusLoading && <p className="text-muted-foreground text-xs">Checking transcription status…</p>}
          {transcript && <Badge variant="review">Machine-generated · review required</Badge>}
        </div>
        {jobError && <ErrorState title="Transcription status unavailable" message={jobError} />}
        {job?.status === "failed" && <ErrorState title="Speech-to-text failed" message={job.error || "The local transcription could not be completed."} />}
        {job?.status === "completed" && !transcript && <ErrorState title="Transcript unavailable" message="The job completed without transcript evidence. Refresh the status to check again." />}

        {transcript && (
          <div className="space-y-4">
            <Alert variant="review">
              <AlertTitle>Review against the recording</AlertTitle>
              <AlertDescription>
                This transcript and its financial cue candidates are machine-generated. Speaker attribution is unavailable;
                statements cannot be assigned to the customer. A human must review the audio before using this evidence.
                It does not establish hardship, eligibility or a recommended action.
              </AlertDescription>
            </Alert>
            <div>
              <h4 className="mb-2 text-sm font-medium">Speech-to-text transcript</h4>
              <p className="bg-muted/40 rounded-md p-3 text-sm leading-relaxed whitespace-pre-line">{transcript.text}</p>
            </div>
            {transcript.segments?.length > 0 && (
              <Collapsible>
                <CollapsibleTrigger asChild>
                  <Button variant="outline" size="sm" className="group">
                    Approximate timestamps <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" aria-hidden />
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-3 rounded-md border">
                  <Table>
                    <caption className="sr-only">Machine-generated transcript segments with approximate timestamps; speakers are not identified</caption>
                    <TableHeader><TableRow><TableHead scope="col">Time</TableHead><TableHead scope="col">Transcript</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {transcript.segments.map((segment, index) => (
                        <TableRow key={index}>
                          <TableCell className="align-top whitespace-nowrap font-mono text-xs">{timestamp(segment.start)}–{timestamp(segment.end)}</TableCell>
                          <TableCell className="align-top text-sm whitespace-pre-line">{segment.text}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CollapsibleContent>
              </Collapsible>
            )}
            <div>
              <h4 className="mb-2 text-sm font-medium">Financial cue candidates</h4>
              <p className="text-muted-foreground mb-2 text-xs">Speaker unknown · unverified</p>
              {cues.length ? (
                <ul className="flex flex-wrap gap-2" aria-label="Machine-generated financial cue candidates">
                  {cues.map(([name]) => <li key={name}><Badge variant="outline">{name.replaceAll("_", " ")}</Badge></li>)}
                </ul>
              ) : <p className="text-muted-foreground text-sm">No configured financial text cue was detected. This does not rule out hardship.</p>}
              <p className="text-muted-foreground mt-2 text-xs">Candidates can reflect either speaker or recognition errors. They are not added to the customer’s brief automatically.</p>
            </div>
            <Collapsible>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm" className="group">
                  Transcription details <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" aria-hidden />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="text-muted-foreground mt-2 space-y-1 text-xs break-words">
                <p>Model: {transcript.model} · detected language: {transcript.language}</p>
                <p>Created {formatDateTime(transcript.created_at)} · audio {timestamp(transcript.duration_sec)} · processing {transcript.processing_seconds.toFixed(1)} seconds</p>
                <p>Source audio SHA-256: <span className="font-mono">{transcript.source_sha256}</span></p>
                <p>Speaker attribution: unavailable · human review: required</p>
              </CollapsibleContent>
            </Collapsible>
          </div>
        )}
      </div>
    </section>
  );
}

export function VoiceEvidence({ customerId }: { customerId: string }) {
  const voice = useApi<CustomerVoice>(`/customers/${encodeURIComponent(customerId)}/voice`);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><AudioLines className="size-5" aria-hidden /> Voice evidence</CardTitle>
        <CardDescription>Listen to linked source recordings and prepare a local speech-to-text transcript for human review.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {voice.loading ? <LoadingState label="Loading voice evidence" rows={2} />
          : voice.error ? <ErrorState title="Voice evidence unavailable" message={voice.error} onRetry={voice.reload} />
            : !voice.data?.items.length ? <EmptyState title="No linked voice recordings" description="No voice sample is linked to this customer’s cases in the release." />
              : <>
                {voice.data.note && <p className="text-muted-foreground text-sm">{voice.data.note}</p>}
                {!voice.data.speech_to_text_available && <Alert>
                  <AlertTitle>Local speech-to-text is not installed</AlertTitle>
                  <AlertDescription>Available recordings can still be played. Install the speech dependencies and model on the server to enable transcription.</AlertDescription>
                </Alert>}
                <p className="text-muted-foreground text-xs">Speech model: {voice.data.speech_model} · processing stays local</p>
                {voice.data.items.map((sample) => <VoiceRecording key={sample.voice_sample_id} sample={sample} speechAvailable={voice.data!.speech_to_text_available} />)}
              </>}
      </CardContent>
    </Card>
  );
}

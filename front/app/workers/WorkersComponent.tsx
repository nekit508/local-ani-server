"use client"

import {useCallback, useEffect, useMemo, useRef, useState} from "react"
import {
    Feed,
    Task,
    WorkerState,
    WorkersFeed,
    deleteTask,
    pauseTask,
    resumeTask,
    retryTask,
    tasksFeed,
    workersFeed,
} from "@/api/api"

const POLL_INTERVAL = 1000

const GROUP_ORDER: Record<string, number> = {
    running: 0,
    queued: 1,
    paused: 2,
    failed: 3,
    done: 4,
}

export default function () {
    const [tasks, setTasks] = useState<Record<number, Task>>({})
    const [workers, setWorkers] = useState<Record<number, WorkerState>>({})
    const [error, setError] = useState<string | null>(null)
    const [busy, setBusy] = useState(false)

    const sinceRef = useRef(0)
    const epochRef = useRef<string | null>(null)
    const pollingRef = useRef(false)

    const poll = useCallback(async (since: number, depth: number = 0): Promise<void> => {
        const [tasksResponse, workersResponse] = await Promise.all([
            tasksFeed(since), workersFeed(since),
        ])

        if (!tasksResponse.ok) {
            setError(tasksResponse.error_str())
            return
        }
        if (!workersResponse.ok) {
            setError(workersResponse.error_str())
            return
        }

        const tasksFeedValue: Feed<Task> = tasksResponse.data()
        const workersFeedValue: WorkersFeed = workersResponse.data()

        if (epochRef.current !== null && tasksFeedValue.epoch !== epochRef.current) {
            // сервер перезапустился: старые ревизии невалидны
            epochRef.current = tasksFeedValue.epoch
            sinceRef.current = 0
            setTasks({})
            setWorkers({})
            if (depth < 2) await poll(0, depth + 1)
            return
        }

        epochRef.current = tasksFeedValue.epoch
        setTasks(previous => {
            const next = {...previous}
            for (const task of tasksFeedValue!.updated) next[task.task_id] = task
            return next
        })
        setWorkers(previous => {
            const next = {...previous}
            for (const worker of workersFeedValue!.updated) next[worker.index] = worker
            return next
        })
        sinceRef.current = Math.max(sinceRef.current, tasksFeedValue.rev, workersFeedValue.rev)
        setError(null)
    }, [])

    const refresh = useCallback(async () => {
        if (pollingRef.current) return
        pollingRef.current = true
        setBusy(true)
        try {
            await poll(sinceRef.current)
        } finally {
            pollingRef.current = false
            setBusy(false)
        }
    }, [poll])

    useEffect(() => {
        sinceRef.current = 0
        epochRef.current = null
        setTasks({})
        setWorkers({})
        void poll(0)

        const timer = setInterval(() => {
            if (pollingRef.current) return
            pollingRef.current = true
            void poll(sinceRef.current).finally(() => {
                pollingRef.current = false
            })
        }, POLL_INTERVAL)

        return () => clearInterval(timer)
    }, [poll])

    const act = useCallback(async (action: (taskId: number) => Promise<unknown>, taskId: number) => {
        await action(taskId)
        await refresh()
    }, [refresh])

    const ordered = useMemo(() => Object.values(tasks).sort((left, right) => {
        const group = (GROUP_ORDER[left.status] ?? 5) - (GROUP_ORDER[right.status] ?? 5)
        if (group !== 0) return group
        return right.rev - left.rev
    }), [tasks])

    const workerList = useMemo(() => Object.values(workers).sort((a, b) => a.index - b.index), [workers])
    const busyWorkers = workerList.filter(worker => worker.state === "busy").length

    return (
        <div className="flex w-full max-w-5xl flex-col gap-4">
            <div className="flex flex-wrap items-center justify-center gap-6 border-b border-foreground/15 pb-4">
                <Stat label="Воркеры" value={ `${busyWorkers} / ${workerList.length || "—"}` }/>
                <Stat label="Задач" value={ ordered.length }/>
                <button className="btn-primary px-3 py-1 text-xs" onClick={ refresh } disabled={ busy }>
                    Обновить
                </button>
            </div>

            { error && <pre className="text-red-700 text-xs whitespace-pre-wrap"> { error } </pre> }

            <div className="flex flex-wrap justify-center gap-4">
                { workerList.map(worker => (
                    <div key={ worker.index } className="default-cornered flex min-w-64 flex-col gap-2 p-3">
                        <div className="flex flex-row justify-between text-xs">
                            <span> Воркер #{ worker.index } </span>
                            <span className={ worker.state === "busy" ? "text-amber-600" : "text-foreground/50" }>
                                { worker.state }
                            </span>
                        </div>
                        { worker.progress ? (
                            <>
                                <span className="text-xs break-words">
                                    { worker.progress.anime } #{ worker.progress.episode } · { worker.progress.dub }
                                </span>
                                <ProgressBar percent={ worker.progress.percent }/>
                                <div className="flex flex-row justify-between text-xs text-foreground/70">
                                    <span> { worker.progress.percent.toFixed(1) }% </span>
                                    <span> { formatSpeed(worker.progress.speed) } </span>
                                    <span> { formatEta(worker.progress.eta) } </span>
                                </div>
                            </>
                        ) : (
                            <span className="text-xs text-foreground/50"> простаивает </span>
                        ) }
                    </div>
                )) }
                { workerList.length === 0 && <span className="text-xs text-foreground/50"> воркеров нет </span> }
            </div>

            <div className="flex flex-col gap-1">
                { ordered.map(task => (
                    <div
                        key={ task.task_id }
                        className={ `default-cornered flex flex-row items-center gap-3 p-2 text-xs
                            ${task.deleted ? "opacity-50" : ""}` }
                    >
                        <span className="w-8 text-center text-foreground/60"> { task.task_id } </span>
                        <div className="flex min-w-0 flex-1 flex-col">
                            <span className="truncate"> { task.title } #{ task.episode } · { task.dub } </span>
                            <span className="truncate text-foreground/50">
                                { task.data_source } · { task.quality ? `${task.quality}p` : "любое качество" }
                                { task.error ? ` · ${task.error}` : "" }
                            </span>
                        </div>
                        <span className="w-48 truncate text-center">
                            { statusLabel(task) }
                            { task.deleted && ` · ${task.deleted_reason ?? "удалено"}` }
                        </span>
                        <div className="w-32">
                            <ProgressBar percent={ task.progress?.percent ?? (task.status === "done" ? 100 : 0) }/>
                        </div>
                        <div className="flex flex-row gap-1">
                            { (task.status === "running" || task.status === "queued") && !task.deleted && (
                                <button className="btn-primary px-2 py-1" title="Пауза"
                                        onClick={ () => act(pauseTask, task.task_id) }> ⏸ </button>
                            ) }
                            { task.status === "paused" && !task.deleted && (
                                <button className="btn-primary px-2 py-1" title="Продолжить"
                                        onClick={ () => act(resumeTask, task.task_id) }> ▶ </button>
                            ) }
                            { task.status === "failed" && !task.deleted && (
                                <button className="btn-primary px-2 py-1" title="Повторить"
                                        onClick={ () => act(retryTask, task.task_id) }> ↻ </button>
                            ) }
                            { !task.deleted && (
                                <button className="btn-primary px-2 py-1" title="Удалить"
                                        onClick={ () => act(deleteTask, task.task_id) }> 🗑 </button>
                            ) }
                        </div>
                    </div>
                )) }
                { ordered.length === 0 && <span className="text-center text-xs text-foreground/50"> пусто </span> }
            </div>
        </div>
    )
}

function statusLabel(task: Task) {
    if (task.progress && (task.status === "running" || task.status === "queued")) {
        const phase = task.progress.phase
        const detail = phase === "download"
            ? `${Math.round(task.progress.percent)}%`
            : phase ?? ""
        return detail ? `${task.status} (${detail})` : task.status
    }
    return task.status
}

function Stat({ label, value }: { label: string, value: string | number }) {
    return (
        <div className="flex flex-col items-center">
            <span className="text-xs text-foreground/50"> { label } </span>
            <span className="text-lg"> { value } </span>
        </div>
    )
}

function ProgressBar({ percent }: { percent: number }) {
    return (
        <div className="h-2 w-full overflow-hidden rounded bg-foreground/10">
            <div
                className="h-full bg-green-600/70 transition-[width]"
                style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
            />
        </div>
    )
}

function formatSpeed(value: number | null | undefined) {
    if (!value) return "—"
    return `${formatBytes(value)}/s`
}

function formatBytes(value: number | null | undefined) {
    if (!value) return "—"
    const units = ["B", "KB", "MB", "GB", "TB"]
    let size = value
    let unit = 0
    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024
        unit += 1
    }
    return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function formatEta(value: number | null | undefined) {
    if (value === null || value === undefined) return "—"
    const seconds = Math.max(0, Math.round(value))
    const minutes = Math.floor(seconds / 60)
    return `${minutes}:${(seconds % 60).toString().padStart(2, "0")}`
}

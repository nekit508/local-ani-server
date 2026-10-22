"use client"

import Image from "next/image"
import {useCallback, useEffect, useMemo, useRef, useState} from "react"
import type {CSSProperties} from "react"
import {
    AnimeInfo,
    Episode,
    Feed,
    MatrixItem,
    Source,
    matrixFeed,
    retryTask,
    startTasks,
} from "@/api/api"
import {rememberState} from "@/api/core-client"

const POLL_INTERVAL = 1000

const QUALITY_OPTIONS = [
    {value: "best", label: "лучшее"},
    {value: "max:1080", label: "≤ 1080p"},
    {value: "max:720", label: "≤ 720p"},
    {value: "max:480", label: "≤ 480p"},
    {value: "max:360", label: "≤ 360p"},
]

function qualityLimit(value: string): number | null {
    if (value === "best") return null
    const [, raw] = value.split(":")
    const limit = Number(raw)
    return Number.isFinite(limit) ? limit : null
}

function keyOf(dub: string, episode: number) {
    return `${dub}|${episode}`
}

export default function ({ anime, dataSource }: { anime: AnimeInfo, dataSource: string }) {
    const columns = useMemo(() => {
        const found = new Map<string, Source>()
        for (const episode of anime.episodes)
            for (const source of episode.sources)
                if (!found.has(source.title)) found.set(source.title, source)
        return [...found.values()]
    }, [anime])

    const [items, setItems] = useState<Record<string, MatrixItem>>({})
    const [error, setError] = useState<string | null>(null)
    const [pending, setPending] = useState<string | null>(null)
    const [quality, setQuality] = rememberState(
        useState("best"),
        "download-quality",
        "best",
        (value: string) => QUALITY_OPTIONS.some(option => option.value === value),
    )

    const sinceRef = useRef(0)
    const epochRef = useRef<string | null>(null)
    const busyRef = useRef(false)

    const applyFeed = useCallback((feed: Feed<MatrixItem>) => {
        setItems(previous => {
            const next = {...previous}
            for (const item of feed.updated) next[keyOf(item.dub, item.episode)] = item
            for (const removed of feed.removed) delete next[keyOf(removed.dub, removed.episode)]
            return next
        })
        sinceRef.current = Math.max(sinceRef.current, feed.rev)
        setError(null)
    }, [])

    const load = useCallback(async (since: number): Promise<void> => {
        const response = await matrixFeed(anime.title, since)
        let restart = false
        response.either(
            feed => {
                if (epochRef.current !== null && feed.epoch !== epochRef.current) {
                    // сервер перезапустился — забираем всё заново
                    epochRef.current = feed.epoch
                    sinceRef.current = 0
                    setItems({})
                    restart = true
                    return
                }
                epochRef.current = feed.epoch
                applyFeed(feed)
            },
            failure => setError(JSON.stringify(failure)),
        )
        if (restart) await load(0)
    }, [anime.title, applyFeed])

    useEffect(() => {
        sinceRef.current = 0
        epochRef.current = null
        setItems({})
        void load(0)

        const timer = setInterval(() => {
            if (busyRef.current) return
            busyRef.current = true
            load(sinceRef.current).finally(() => {
                busyRef.current = false
            })
        }, POLL_INTERVAL)

        return () => clearInterval(timer)
    }, [load])

    const start = useCallback(async (column: Source, episodes: Episode[]) => {
        if (episodes.length === 0) return
        setPending(column.title)
        const response = await startTasks({
            data_source: dataSource,
            title: anime.title,
            dub: column.dub,
            episodes: episodes.map(episode => episode.ordinal),
            quality: qualityLimit(quality),
        })
        response.either(
            result => {
                const failed = Object.entries(result.errors)
                setError(
                    failed.length === 0
                        ? null
                        : failed.map(([ordinal, message]) => `${ordinal}: ${message}`).join("\n"),
                )
            },
            failure => setError(JSON.stringify(failure)),
        )
        setPending(null)
        await load(sinceRef.current)
    }, [anime.title, dataSource, quality, load])

    const retry = useCallback(async (taskId: number) => {
        await retryTask(taskId)
        await load(sinceRef.current)
    }, [load])

    const cells = anime.episodes.reduce(
        (total, episode) => total + episode.sources.length, 0,
    )
    const downloaded = Object.values(items).filter(item => item.exists).length

    return (
        <div className="flex flex-col items-center justify-start h-full gap-4 m-4">
            <div className="flex flex-row items-center justify-center gap-4 w-full border-b border-foreground/15 pb-4">
                <Image src={"https:" + anime.thumbnail} alt={anime.title} width={256} height={256} className="object-cover"/>
                <div className="flex flex-col items-start justify-center gap-6">
                    <span className="text-xl"> { anime.title } </span>
                    <span className="text-xs"> { anime.description } </span>
                </div>
            </div>

            <div className="flex flex-row flex-wrap items-center justify-center gap-4 text-sm">
                <span> Скачано: { downloaded } / { cells } </span>
                <label className="flex flex-row items-center gap-2 text-xs">
                    <span className="text-foreground/60"> качество </span>
                    <select
                        className="default-cornered p-1 text-xs"
                        value={ quality }
                        onChange={ event => setQuality(event.target.value) }
                    >
                        { QUALITY_OPTIONS.map(option => (
                            <option key={ option.value } value={ option.value }> { option.label } </option>
                        )) }
                    </select>
                </label>
                { pending && <span className="text-foreground/60 text-xs"> { pending }… </span> }
            </div>

            { error && (
                <pre className="text-red-700 text-xs whitespace-pre-wrap max-w-full"> { error } </pre>
            ) }

            <EpisodesTable
                episodes={ anime.episodes }
                columns={ columns }
                items={ items }
                pending={ pending }
                onStart={ start }
                onRetry={ retry }
            />
        </div>
    )
}

function EpisodesTable(
    {
        episodes, columns, items, pending, onStart, onRetry,
    }: {
        episodes: Episode[]
        columns: Source[]
        items: Record<string, MatrixItem>
        pending: string | null
        onStart: (column: Source, episodes: Episode[]) => void
        onRetry: (taskId: number) => void
    },
) {
    const missing = (column: Source) => episodes.filter(episode => {
        const source = episode.sources.find(candidate => candidate.title === column.title)
        if (!source) return false
        return !items[keyOf(column.dub, episode.ordinal)]?.exists
    })

    return (
        <div
            className="grid gap-1 grid-cols-[repeat(var(--cols),minmax(0,1fr))] items-stretch w-full max-w-3xl"
            style={{ "--cols": columns.length + 1 } as CSSProperties}
        >
            <div className=""/>
            { columns.map(column => (
                <div key={ column.title } className="flex flex-col items-center gap-1 p-1">
                    <span className="text-xs text-center break-words"> { column.title } </span>
                    <button
                        className="btn-primary px-2 py-1 text-xs"
                        disabled={ pending !== null }
                        title={ `Скачать недостающие (${missing(column).length})` }
                        onClick={ () => onStart(column, missing(column)) }
                    >
                        ↓ { missing(column).length }
                    </button>
                </div>
            )) }

            { episodes.map(episode => (
                <Row
                    key={ episode.ordinal }
                    episode={ episode }
                    columns={ columns }
                    items={ items }
                    onStart={ onStart }
                    onRetry={ onRetry }
                />
            )) }
        </div>
    )
}

function Row(
    {
        episode, columns, items, onStart, onRetry,
    }: {
        episode: Episode
        columns: Source[]
        items: Record<string, MatrixItem>
        onStart: (column: Source, episodes: Episode[]) => void
        onRetry: (taskId: number) => void
    },
) {
    return (
        <>
            <span className="text-center text-xs self-center"> { episode.ordinal } </span>
            { columns.map(column => {
                const hasSource = episode.sources.some(source => source.title === column.title)
                return (
                    <div key={ `${episode.ordinal}$$${column.title}` } className="min-h-8">
                        { hasSource
                            ? <Cell
                                item={ items[keyOf(column.dub, episode.ordinal)] }
                                onStart={ () => onStart(column, [episode]) }
                                onRetry={ onRetry }
                            />
                            : <div className="min-h-8 rounded bg-foreground/5"/> }
                    </div>
                )
            }) }
        </>
    )
}

function Cell(
    { item, onStart, onRetry }: {
        item: MatrixItem | undefined
        onStart: () => void
        onRetry: (taskId: number) => void
    },
) {
    const base = "flex min-h-8 w-full items-center justify-center rounded text-xs"

    if (!item) {
        return <button className={ `${base} btn-primary` } title="Скачать" onClick={ onStart }> ↓ </button>
    }
    if (item.exists) {
        return <div className={ `${base} bg-green-600/70 text-white` } title={ item.ext ? `.${item.ext}` : "" }> ✓ </div>
    }

    const task = item.task
    if (!task) {
        return <button className={ `${base} btn-primary` } title="Скачать" onClick={ onStart }> ↓ </button>
    }

    switch (task.status) {
        case "failed":
            return (
                <button className={ `${base} bg-red-600/60 text-white` } title={ "Повторить" } onClick={ () => onRetry(task.task_id) }>
                    ↻
                </button>
            )
        case "paused":
            return <div className={ `${base} bg-foreground/20` } title="Пауза"> ⏸ </div>
        case "running":
        case "queued":
            return <div className={ `${base} bg-amber-500/40` } title={ task.status }> { Math.round(task.percent) }% </div>
        default:
            return <div className={ `${base} bg-foreground/20` } title={ task.status }> { task.status } </div>
    }
}

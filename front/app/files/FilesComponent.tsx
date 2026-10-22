"use client"

import {useCallback, useEffect, useState} from "react"
import {FileEntry, FilesListing, deleteFile, listFiles} from "@/api/api"

export default function () {
    const [path, setPath] = useState("")
    const [listing, setListing] = useState<FilesListing | null>(null)
    const [selected, setSelected] = useState<FileEntry | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [copied, setCopied] = useState<string | null>(null)

    const load = useCallback(async (target: string) => {
        const response = await listFiles(target)
        response.either(
            data => {
                setListing(data)
                setSelected(null)
                setError(null)
            },
            failure => setError(JSON.stringify(failure)),
        )
    }, [])

    useEffect(() => {
        load(path)
    }, [load, path])

    const copy = useCallback(async (value: string, kind: string) => {
        try {
            await navigator.clipboard.writeText(value)
            setCopied(kind)
            setTimeout(() => setCopied(null), 1500)
        } catch {
            setCopied(null)
        }
    }, [])

    const remove = useCallback(async (item: FileEntry) => {
        const response = await deleteFile(item.path)
        response.either(
            () => setError(null),
            failure => setError(JSON.stringify(failure)),
        )
        if (selected?.path === item.path) setSelected(null)
        await load(path)
    }, [load, path, selected])

    const current = listing?.path ?? path
    const segments = current.split("/").filter(Boolean)

    return (
        <div className="flex w-full max-w-4xl flex-col gap-4">
            <div className="flex flex-row flex-wrap items-center justify-between gap-2 border-b border-foreground/15 pb-2 text-xs">
                <div className="flex flex-row flex-wrap items-center gap-1">
                    <button className="btn-primary px-2 py-1" onClick={ () => setPath("") }> root </button>
                    { segments.map((segment, index) => (
                        <span key={ `${index}-${segment}` } className="flex flex-row items-center gap-1">
                            <span className="text-foreground/40"> / </span>
                            <button
                                className="btn-primary px-2 py-1"
                                onClick={ () => setPath(segments.slice(0, index + 1).join("/")) }
                            >
                                { segment }
                            </button>
                        </span>
                    )) }
                </div>
                <div className="flex flex-row gap-2">
                    { listing?.parent !== null && listing?.parent !== undefined && (
                        <button className="btn-primary px-2 py-1" onClick={ () => setPath(listing.parent as string) }>
                            ↑ вверх
                        </button>
                    ) }
                    <button className="btn-primary px-2 py-1" onClick={ () => load(path) }> Обновить </button>
                </div>
            </div>

            { error && <pre className="text-red-700 text-xs whitespace-pre-wrap"> { error } </pre> }

            <div className="flex flex-col gap-1">
                { listing?.items.map(item => (
                    <div
                        key={ item.path }
                        className={ `default-cornered flex flex-row items-center justify-between gap-2 p-2 text-xs
                            ${selected?.path === item.path ? "ring-2 ring-accent/60" : ""}` }
                    >
                        <button
                            className="flex min-w-0 flex-1 flex-row items-center gap-2 text-left"
                            onClick={ () => item.type === "dir" ? setPath(item.path) : setSelected(item) }
                        >
                            <span className="w-5 text-center"> { item.type === "dir" ? "📁" : "🎬" } </span>
                            <span className="truncate"> { item.name } </span>
                        </button>
                        <span className="w-20 text-right text-foreground/60">
                            { item.type === "dir" ? "—" : formatBytes(item.size) }
                        </span>
                        <span className="w-40 text-right text-foreground/50">
                            { formatTime(item.mtime) }
                        </span>
                        <button
                            className="btn-primary px-2 py-1"
                            title={ item.type === "dir" ? "Удалить пустую папку" : "Удалить файл" }
                            onClick={ () => remove(item) }
                        >
                            🗑
                        </button>
                    </div>
                )) }
                { listing && listing.items.length === 0 && (
                    <span className="text-center text-xs text-foreground/50"> пусто </span>
                ) }
            </div>

            { selected && listing && (
                <div className="flex flex-col gap-2 border-t border-foreground/15 pt-4 text-xs">
                    <span className="text-sm"> { selected.name } </span>
                    <span className="text-foreground/60"> { formatBytes(selected.size) } · { formatTime(selected.mtime) } </span>
                    <PathRow
                        label="путь на диске"
                        value={ `${listing.root}/${selected.path}` }
                        copied={ copied === "absolute" }
                        onCopy={ () => copy(`${listing.root}/${selected.path}`, "absolute") }
                    />
                    <PathRow
                        label="относительно DOWNLOAD_DIR"
                        value={ selected.path }
                        copied={ copied === "relative" }
                        onCopy={ () => copy(selected.path, "relative") }
                    />
                    <span className="text-foreground/40">
                        Из этого относительного пути потом собирается URL для nginx.
                    </span>
                </div>
            ) }
        </div>
    )
}

function PathRow(
    { label, value, copied, onCopy }: {
        label: string
        value: string
        copied: boolean
        onCopy: () => void
    },
) {
    return (
        <div className="flex flex-row items-center gap-2">
            <span className="w-48 text-foreground/50"> { label } </span>
            <code className="min-w-0 flex-1 truncate rounded bg-foreground/5 p-1"> { value } </code>
            <button className="btn-primary px-2 py-1" onClick={ onCopy }>
                { copied ? "скопировано" : "копировать" }
            </button>
        </div>
    )
}

function formatBytes(value: number | null | undefined) {
    if (value === null || value === undefined) return "—"
    const units = ["B", "KB", "MB", "GB", "TB"]
    let size = value
    let unit = 0
    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024
        unit += 1
    }
    return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function formatTime(value: number) {
    if (!value) return "—"
    const date = new Date(value * 1000)
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString()
}

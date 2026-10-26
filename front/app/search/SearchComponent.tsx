"use client"

import {SearchedAnime, search, DataSource} from "@/api/api";
import {useState} from "react";
import {waited} from "@/api/core";
import APIFail from "@/components/APIFail";
import {rememberState, useWaitedState} from "@/api/core-client";
import Image from "next/image";
import Link from "next/link";

export default function ({ sources }: { sources: DataSource[] }) {
    const [searchQuery, setSearchQuery] = useState("")
    const [list, setList] = useWaitedState<SearchedAnime[]>(null)
    const [source, setSource] = rememberState(useState(""), "name", "", v => sources.includes(v))

    const performSearch =  () => {
        setList(undefined)
        waited([search(source, searchQuery), null], setList, () => setList(null))
    }

    return (
        <form onSubmit={(e) => {
            e.preventDefault()
            performSearch()
        }}>
            <div className="flex flex-col gap-4 items-center size-ful mt-4">
                <div className="flex flex-row gap-4 items-center">
                    <input className="input" onChange={(e) => setSearchQuery(e.target.value)}/>
                    <button type="submit" className="btn-primary w-16" disabled={source === "" || searchQuery.length == 0}> Search </button>
                    { list !== undefined && list !== null && !list.ok && <APIFail message={list.error_str()}/> }
                    <select value={source} className="default-cornered p-2" onChange={e => setSource(e.target.value)}>
                        { sources.map((v, i) => (<option key={i.toString()}> {v} </option>)) }
                    </select>
                </div>
                <div className="flex flex-col gap-4 justify-start items-start">
                    { list?.ok && list.data().map(anime => {
                        return (
                            <div key={anime.title} className="flex flex-row justify-center items-center gap-4">
                                { anime.thumbnail && <Image src={"https:" + anime.thumbnail} alt={anime.title} width={64} height={64} className="object-cover"/> }
                                <Link href={`/anime?title=${anime.title}&source=${source}`}>
                                    <span className="wrap-break-word"> {anime.title} </span>
                                </Link>
                            </div>
                        )
                    }) }
                </div>
            </div>
        </form>
    )
}
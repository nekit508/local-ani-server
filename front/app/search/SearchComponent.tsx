"use client"

import {useState} from "react";
import {waited} from "@/api/core";
import APIFail from "@/components/APIFail";
import {rememberState, useWaitedState} from "@/api/core-client";
import Image from "next/image";
import Link from "next/link";
import {Extractor, search, ProtoAnime} from "@/api/search";

export default function ({ extractors }: { extractors: Extractor[] }) {
    const [searchQuery, setSearchQuery] = useState("")
    const [list, setList] = useWaitedState<ProtoAnime[]>(null)
    const [extractor, setExtractor] = rememberState(useState(""), "name", "", v => extractors.find(e => e.name == v) !== undefined)

    const performSearch =  () => {
        setList(undefined)
        waited([search(extractor, searchQuery), null], setList, () => setList(null))
    }

    return (
        <form onSubmit={(e) => {
            e.preventDefault()
            performSearch()
        }}>
            <div className="flex flex-col gap-4 items-center size-ful mt-4">
                <div className="flex flex-row gap-4 items-center">
                    <input className="input" onChange={(e) => setSearchQuery(e.target.value)}/>
                    <button type="submit" className="btn-primary w-16" disabled={extractor === "" || searchQuery.length == 0}> Search </button>
                    { list !== undefined && list !== null && !list.ok && <APIFail message={list.error_str()}/> }
                    <select value={extractor} className="default-cornered p-2" onChange={e => setExtractor(e.target.value)}>
                        { extractors.map((v, i) => (<option key={i.toString()}> {v.name} </option>)) }
                    </select>
                </div>
                <div className="flex flex-col gap-4 justify-start items-start">
                    { list?.ok && list.data().map(anime => {
                        return (
                            <div key={anime.title} className="flex flex-row justify-center items-center gap-4">
                                { anime.thumbnail_url && <Image src={"https:" + anime.thumbnail_url} alt={anime.title} width={64} height={64} className="object-cover"/> }
                                <Link href={`/anime?title=${anime.id}&extractor=${extractor}`}>
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
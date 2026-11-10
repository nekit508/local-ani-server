"use server"

import SearchComponent from "@/app/search/SearchComponent";
import APIFail from "@/components/APIFail";
import {extractors} from "@/api/search";

export default async function () {
    const res = await extractors()

    return res.ok ? (
        <div className="flex flex-col items-center">
            <SearchComponent extractors={res.data()}/>
        </div>
    ) : (
        <APIFail message={res.error_str()}/>
    )
}
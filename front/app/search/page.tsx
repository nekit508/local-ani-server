"use server"

import {dataSources} from "@/api/api";
import SearchComponent from "@/app/search/SearchComponent";
import APIFail from "@/components/APIFail";

export default async function () {
    const res = await dataSources()

    return res.ok ? (
        <div className="flex flex-col items-center">
            <SearchComponent sources={res.data()}/>
        </div>
    ) : (
        <APIFail message={res.error_str()}/>
    )
}
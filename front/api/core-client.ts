"use client"

import {RestResponse} from "@/api/types";
import {Dispatch, SetStateAction, useEffect, useState} from "react";

export function useWaitedState<T>(def: RestResponse<T> | null = null) {
    return useState<RestResponse<T> | null | undefined>(def)
}

export function rememberState<T, D>(args : [T | D, Dispatch<SetStateAction<T | D>>], name: string, def: D, validator: (value: T) => boolean = () => true) : [T | D, Dispatch<SetStateAction<T | D>>] {
    const [get, set] = args
    useEffect(() => {
        const str = localStorage.getItem(name)
        if (str) {
            let value = null;
            try {
                value = JSON.parse(str) as T
                if (validator(value))
                    set(value)
                else {
                    localStorage.removeItem(name)
                    set(def)
                }
            } catch (e) {
                localStorage.removeItem(name)
                set(def)
            }
        }
    }, []);

    useEffect(() => {
        if (get != def)
            localStorage.setItem(name, JSON.stringify(get))
    }, [get]);

    return [get, set]
}
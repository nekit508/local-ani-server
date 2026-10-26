export class RestResponse<T> {
    ok: boolean
    body: T | RestError

    constructor(body: T | RestError, ok: boolean) {
        this.ok = ok
        this.body = body;
    }

    public either<R1, R2>(onSuccess: (body: T) => R1, onError: (error: RestError) => R2 ): R1 | R2 {
        return this.ok ? onSuccess(this.body as T) : onError(this.body as RestError)
    }

    public map<O>(mapper: (body: T) => O) {
        return new RestResponse(this.ok ? mapper(this.body as T) : (this.body as RestError), this.ok)
    }

    public noResponse(): RestResponse<null> {
        return new RestResponse(this.ok ? null : this.body as RestError, this.ok)
    }

    public data() {
        return this.body as T
    }

    public error() {
        return this.body as RestError
    }

    public error_str() {
        const e = this.error()
        return JSON.stringify(e)
    }
}

export type RestError = {
    code: number
    body: any
}
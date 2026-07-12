## Retry policy

The client MUST retry a failed request at most 5 times. Between attempts it MUST wait no less than 200 ms and no more than 2000 ms. If the server returns `429`, the client MUST NOT retry before the `Retry-After` interval has elapsed.

The system should be robust, intuitive, and user-friendly under all conditions.

The client SHALL log each retry with the attempt number and the elapsed time. It SHOULD surface a warning to the operator when the retry budget is exhausted.

    curl -sS --retry 5 --retry-delay 2 https://api.example.com/v1/ping

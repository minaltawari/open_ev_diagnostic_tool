def decode_nrc_code(nrc_byte):

    nrc_dictionary = {
        0x10: "GeneralReject",
        0x11: "ServiceNotSupported",
        0x12: "SubFunctionNotSupported",
        0x13: "IncorrectMessageLengthOrInvalidFormat",
        0x14: "ResponseTooLong",
        0x21: "BusyRepeatRequest",
        0x22: "ConditionsNotCorrect",
        0x24: "RequestSequenceError",
        0x25: "NoResponseFromSubnetComponent",
        0x26: "FailurePreventsExecutionOfRequestedAction",
        0x31: "RequestOutOfRange",
        0x33: "SecurityAccessDenied",
        0x35: "InvalidKey",
        0x36: "ExceedNumberOfAttempts",
        0x37: "RequiredTimeDelayNotExpired",
        0x70: "UploadDownloadNotAccepted",
        0x71: "TransferDataSuspended",
        0x72: "GeneralProgrammingFailure",
        0x73: "WrongBlockSequenceCounter",
        0x78: "ResponsePending",
        0x7E: "SubFunctionNotSupportedInActiveSession",
        0x7F: "ServiceNotSupportedInActiveSession"
    }

    return nrc_dictionary.get(
        nrc_byte,
        f"Unknown NRC 0x{nrc_byte:02X}"
    )


def evaluate_response(
    sid,
    request_payload,
    response_payload
):

    if not response_payload:

        return (
            False,
            "Diagnostic Session Timeout: Node failed to respond.",
            b""
        )

    if response_payload[0] == 0x7F:

        nrc = response_payload[2] if len(response_payload) >= 3 else 0x00

        return (
            False,
            f"[-] Negative Response Code (NRC): {decode_nrc_code(nrc)}",
            b""
        )

    positive_sid = sid + 0x40

    if response_payload[0] == positive_sid:

        if sid == 0x22:

            data = response_payload[3:]

        elif sid == 0x14:

            data = response_payload[4:]

        else:

            data = response_payload[1:]

        return (
            True,
            "[+] Positive Validation Frame Acknowledged!",
            data
        )

    return (
        False,
        "[-] Unexpected Protocol Frame Format Mismatch Error.",
        b""
    )

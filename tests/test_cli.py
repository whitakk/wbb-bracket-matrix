from bracket_matrix.cli import build_parser


def test_cli_auth_login_defaults():
    parser = build_parser()
    args = parser.parse_args(["auth-login"])

    assert args.command == "auth-login"
    assert args.source == "the_athletic"
    assert args.output is None
    assert args.url is None


def test_cli_auth_login_custom_args():
    parser = build_parser()
    args = parser.parse_args(
        [
            "auth-login",
            "--source",
            "the_athletic",
            "--output",
            "data/custom_athletic_state.json",
            "--url",
            "https://www.nytimes.com/athletic/tag/bracketcentral/",
        ]
    )

    assert args.command == "auth-login"
    assert args.source == "the_athletic"
    assert str(args.output) == "data/custom_athletic_state.json"
    assert args.url == "https://www.nytimes.com/athletic/tag/bracketcentral/"


def test_cli_check_athletic_update_defaults():
    parser = build_parser()
    args = parser.parse_args(["check-athletic-update"])

    assert args.command == "check-athletic-update"
    assert args.notify_email == ""
    assert str(args.state_file).endswith("data/manual/the_athletic_latest_url.txt")
    assert args.use_playwright is False

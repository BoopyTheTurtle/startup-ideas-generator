from pipeline.robots import allowed, parse

UA = "startup-ideas-generator"


def test_mid_path_wildcard_blocks_apple_feed():
    g = parse("User-agent: *\nDisallow: /*/rss/*\n")
    assert not allowed(g, UA, "https://itunes.apple.com/gb/rss/customerreviews/page=1/id=1/json")
    assert allowed(g, UA, "https://itunes.apple.com/gb/app/foo/id1")


def test_longest_match_wins_and_allow_wins_ties():
    g = parse("User-agent: *\nDisallow: /forum/\nAllow: /forum/feeds/\nDisallow: /x\nAllow: /x\n")
    assert not allowed(g, UA, "https://a.b/forum/thread/1")
    assert allowed(g, UA, "https://a.b/forum/feeds/latest.rss")
    assert allowed(g, UA, "https://a.b/x")


def test_dollar_anchor():
    g = parse("User-agent: *\nDisallow: /*.rss$\n")
    assert not allowed(g, UA, "https://a.b/feed.rss")
    assert allowed(g, UA, "https://a.b/feed.rss?page=2")


def test_specific_group_overrides_star():
    g = parse("User-agent: *\nDisallow: /\n\nUser-agent: startup-ideas-generator\nAllow: /\n")
    assert allowed(g, UA, "https://a.b/anything")


def test_named_ai_crawler_block_does_not_apply_to_us_but_star_does():
    g = parse("User-agent: ClaudeBot\nUser-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nDisallow: /private\n")
    assert allowed(g, UA, "https://a.b/public")
    assert not allowed(g, UA, "https://a.b/private/x")


def test_empty_disallow_and_query_paths():
    g = parse("User-agent: *\nDisallow:\nDisallow: /search?q=\n")
    assert allowed(g, UA, "https://a.b/")
    assert not allowed(g, UA, "https://a.b/search?q=x")


def test_robots_txt_itself_always_allowed():
    assert allowed(parse("User-agent: *\nDisallow: /\n"), UA, "https://a.b/robots.txt")


def test_bom_does_not_drop_first_group():
    assert not allowed(parse("﻿User-agent: *\nDisallow: /\n"), UA, "https://a.b/x")


def test_agent_names_match_exactly_not_as_substrings():
    g = parse("User-agent: *\nDisallow: /\n\nUser-agent: s\nAllow: /\n")
    assert not allowed(g, UA, "https://a.b/x")


def test_percent_encoded_unreserved_chars_match():
    g = parse("User-agent: *\nDisallow: /~joe\n")
    assert not allowed(g, UA, "https://a.b/%7Ejoe/x")


def test_unknown_lines_do_not_split_agent_group():
    g = parse("User-agent: other\nCrawl-delay: 5\nUser-agent: *\nDisallow: /\n")
    assert not allowed(g, UA, "https://a.b/x")

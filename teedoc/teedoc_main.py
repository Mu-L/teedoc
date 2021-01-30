import argparse
import sys
try:
    from .logger import Logger
except Exception:
    from logger import Logger
import os, sys
import json
import subprocess
import shutil
import re
from collections import OrderedDict
import multiprocessing
import threading
import math

def split_list(obj, n):
    dist = math.ceil(len(obj)/n)
    for i in range(0, len(obj), dist):
        yield obj[i:i+dist]

def get_content_type_by_path(file_path):
    ext = os.path.splitext(file_path)[1][1:].lower()
    content_type = "text/plain"
    if ext == "svg":
        content_type = "image/svg+xml"
    elif ext == "html":
        content_type = "text/html"
    elif ext == "jpeg" or ext == "jpg" or ext == "png":
        content_type = "image/{}".format(ext)
    elif ext == "css":
        content_type = "text/css"
    elif ext == "js":
        content_type = "application/javascript"

    return content_type

def parse_site_config(doc_src_path):
    site_config_path = os.path.join(doc_src_path, "site_config.json")
    def check_site_config(config):
        configs = ["site_name", "site_slogon", "site_root_url", "route", "executable", "plugins"]
        for c in configs:
            if not c in config:
                return False, "need {} keys, see example docs".format(configs)
        return True, ""
    if not os.path.exists(site_config_path):
        return False, "can not find site config file: {}".format(site_config_path)
    with open(site_config_path, encoding="utf-8") as f:
        try:
            site_config = json.load(f)
        except Exception as e:
            return False, "can not parse json file, json format error: {}".format(e)
    ok, msg = check_site_config(site_config)
    if not ok:
        return False, "check site_config.json fail: {}".format(msg)
    return True, site_config

def copy_dir(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True

def copy_file(src, dst):
    dir = os.path.dirname(dst)
    if not os.path.exists(dir):
        os.makedirs(dir)
    shutil.copyfile(src, dst)
    return True

def get_files(dir_path):
    result = []
    files = os.listdir(dir_path)
    if not files:
        return []
    for name in files:
        path = os.path.join(dir_path, name)
        if os.path.isdir(path):
            f_list = get_files(path)
            result.extend(f_list)
        else:
            result.append(path)
    return result

def write_to_file(files_content, in_path, out_path):
    '''
        @files_content      { "/home/neucrack/site/docs/get_started/zh/README.md": "<h1>index page</h1>"
        @in_path      "/home/neucrack/site/docs/get_started/zh"
        @out_path     "/home/neucrack/site/out/get_started/zh"
    '''
    for file, html in files_content.items():
        f_path = file.replace(in_path, out_path)
        d_path = os.path.dirname(f_path)
        if not os.path.exists(d_path):
            os.makedirs(d_path)
        # TODO: check file update, if not, skip
        if html: # html, change name
            if os.path.basename(f_path).lower() == "readme.md": # change readme.md to index.html
                f_path = os.path.join(os.path.dirname(f_path), "index.html")
            else:
                f_path = "{}.html".format(os.path.splitext(f_path)[0])
            with open(f_path, "w", encoding="utf-8") as f:
                f.write(html)
        else:    # normal files, just copy
            with open(f_path, "wb") as f:
                with open(file, "rb") as s:
                    f.write(s.read())
    return True, ""

def get_sidebar(doc_dir):
    sidebar_config_path = os.path.join(doc_dir, "sidebar.json")
    with open(sidebar_config_path, encoding="utf-8") as f:
        return json.load(f)

def get_navbar(doc_dir):
    sidebar_config_path = os.path.join(doc_dir, "config.json")
    with open(sidebar_config_path, encoding="utf-8") as f:
        return json.load(f)['navbar']

def get_footer(doc_dir):
    sidebar_config_path = os.path.join(doc_dir, "config.json")
    with open(sidebar_config_path, encoding="utf-8") as f:
        return json.load(f)['footer']

def get_url_by_file(file_path, doc_url):
    url = os.path.splitext(file_path)[0]
    tmp = os.path.split(url)
    if tmp[1].lower() == "readme":
        url = "{}/index".format(tmp[0])
        if url.startswith("/"):
            url = url[1:]
    url = "{}/{}.html".format(doc_url, url)
    return url

def get_sidebar_list(sidebar, doc_path, doc_url):
    '''
        @return {
            "file_path": {
                "curr": (url, label),
                "previous": (url, label),
                "next": (url, label),
            }
        }
    '''
    def get_items(config, doc_url, level=0):
        '''
            @return {
                "file_path": {
                    "curr": (url, label),
                }
            }
        '''
        is_dir = "items" in config
        items = OrderedDict()
        if "label" in config and "file" in config and config["file"] != None and config["file"] != "null":
            url = get_url_by_file(config["file"], doc_url)
            items[os.path.join(doc_path, config["file"])] = {
                "curr": (url, config["label"])
            }
        if is_dir:
            for item in config["items"]:
                _items = get_sidebar_list(item, doc_path, doc_url)
                items.update(_items)
        return items

    dict_items = get_items(sidebar, doc_url)
    items = list(dict_items.items())
    length = len(items)
    for i, (path, item) in enumerate(items):
        p = None
        n = None
        if i > 0:
            p = items[i - 1][1]["curr"]
        if i < length - 1:
            n = items[i + 1][1]["curr"]
        item["previous"] = p
        item["next"] = n
        dict_items[path]= item
    return dict_items

def generate_sidebar_html(htmls, sidebar, doc_path, doc_url, sidebar_title_html):
    '''
        @htmls  {
                "file1_path": {
                                "title": "",
                                "desc": "",
                                "keywords": [],
                                "body": html
                                }
                }
        @return {
                "file1_path": {
                                "title": "",
                                "desc": "",
                                "keywords": [],
                                "body": html，
                                “sidebar": ""
                                }
                }
    '''
    def generate_items(config, doc_path_relative, doc_url, level=0):
        html = ""
        li = False
        is_dir = "items" in config
        active = False
        li_item_html = ""
        if "label" in config:
            if "file" in config and config["file"] != None and config["file"] != "null":
                url = get_url_by_file(config["file"], doc_url)
                active = doc_path_relative == config["file"]
                li_item_html = '<li class="{} with_link"><a href="{}"><span class="label">{}</span><span class="{}"></span></a>'.format(
                    "active" if active else "not_active",
                    url, config["label"],
                    "sub_indicator" if is_dir else ""
                )
            elif "url" in config and config["url"] != None and config["url"] != "null":
                li_item_html = '<li class="{} with_link"><a href="{}" {}><span class="label">{}</span><span class="{}"></span></a>'.format(
                    "not_active",
                    config["url"],
                    'target="{}"'.format(config["target"]) if "target" in config else "",
                    config["label"],
                    "sub_indicator" if is_dir else ""
                )
            else:
                li_item_html = '<li class="not_active no_link"><a><span class="label">{}</span><span class="{}"></span></a>'.format(
                    config["label"], "sub_indicator" if is_dir else ""
                )
            li = True
        if is_dir:
            dir_html = ""
            _active = False
            for item in config["items"]:
                item_html, _active_sub = generate_items(item, doc_path_relative, doc_url, level + 1)
                _active |= _active_sub
                dir_html += item_html
            active |= _active
            if _active:
                li_item_html = li_item_html.replace("not_active", 'active_parent')
            elif not active:
                li_item_html = li_item_html.replace("sub_indicator", "sub_indicator sub_indicator_collapsed")
            html += li_item_html
            html += '<ul class="{}">\n{}</ul>\n'.format("show" if active else "", dir_html)
        else:
            html += li_item_html
        if li:
            html += "</li>\n"
        return html, active


    for file, html in htmls.items():
        if not html:
            continue
        doc_path_relative = file.replace(doc_path, "")[1:].replace("\\", "/")
        items, _ = generate_items(sidebar, doc_path_relative, doc_url)
        sidebar_html = '''
            <div id="sidebar_wrapper">
                <div id="sidebar">
                    <div id="sidebar_title">
                        {}
                    </div>
                    {}
                </div>
            </div>'''.format(sidebar_title_html, items)
        html["sidebar"] = sidebar_html
        htmls[file] = html
    return htmls

def generate_navbar_html(htmls, navbar, doc_path, doc_url, plugins_objs):
    '''
        @doc_path  doc path, contain config.json and sidebar.json
        @doc_url   doc url, config in "route" of site_config.json
        @htmls  {
                "file1_path": {
                                "title": "",
                                "desc": "",
                                "keywords": [],
                                "body": html,
                                “sidebar": ""
                                }
                }
        @return {
                "file1_path": {
                                "title": "",
                                "desc": "",
                                "keywords": [],
                                "body": html，
                                "sidebar": "",
                                "navbar": ""
                                }
                }
    '''
    def generate_items(config, doc_url, level):
        li = False
        active_item = None
        have_label = "label" in config
        li_html = ""
        active = False
        if have_label and "url" in config and config["url"] != None and config["url"] != "null":
            if not config["url"].startswith("http"):
                if not config["url"].startswith("/"):
                    config["url"] = "/{}".format(config["url"])
            active = doc_url == config["url"]
            if active:
                active_item = config
            li = True
        sub_items_ul_html = ""
        if "items" in config:
            active_item = None
            sub_items_html = ""
            for item in config["items"]:
                item_html, _active_item = generate_items(item, doc_url, level + 1)
                if _active_item:
                    active_item = _active_item
                sub_items_html += item_html
            sub_items_ul_html = "<ul>{}</ul>".format(sub_items_html)
        if not li:
            li_html = '<li class="sub_items"><a>{}{}</a>{}\n'.format("{}".format(config["label"]) if have_label else "",
                                active_item["label"] if active_item else "",
                                sub_items_ul_html
                        )
        else:
            li_html = '<li class="{}"><a {} href="{}">{}</a>{}'.format(
                "active" if active else '',
                'target="{}"'.format(config["target"]) if "target" in config else "",
                config["url"], config["label"], sub_items_ul_html
            )
        html = '{}</li>\n'.format(li_html)
        return html, active_item
    
    def generate_lef_right_items(config, doc_url):
        left = '<ul id="nav_left">\n'
        right = '<ul id="nav_right">\n'
        for item in config["items"]:
            html, _ = generate_items(item, doc_url, 0)
            if "position" in item and item["position"] == "right":
                right += html
            else:
                left  += html
        left += "</ul>\n"
        right += "</ul>\n"
        return left, right

    for file, html in htmls.items():
        if not html:
            continue
        nav_left, nav_right = generate_lef_right_items(navbar, doc_url)
        logo_html = '<a class="site_title" href="{}"><img class="site_logo" src="{}" alt="{}"><h2>{}</h2></a>'.format(
                        navbar["home_url"], navbar["logo"]["src"], navbar["logo"]["alt"], navbar["title"]
                     )
        # add navbar items from plugins
        items_plugins_html = ""
        for plugin in plugins_objs:
            _items = plugin.on_add_navbar_items()
            if not _items:
                continue
            items_html = '<ul id="nav_plugins">'
            for item in _items:
                items_html += "<li>{}</li>".format(item)
            items_html += "</ul>"
            items_plugins_html += items_html
        navbar_html = '''
            <div id="navbar">
                <div id="navbar_menu">
                    {}
                    <a id="navbar_menu_btn"></a>
                </div>
                <div id="navbar_items">
                    <div>
                        {}
                    </div>
                    <div>
                        {}
                        {}
                    </div>
                </div>
            </div>'''.format(logo_html, nav_left, nav_right, items_plugins_html)
        html["navbar"] = navbar_html
        htmls[file] = html
    return htmls

def generate_footer_html(htmls, footer, doc_path, doc_url, plugins_objs):
    '''
        @doc_path  doc path, contain config.json and sidebar.json
        @doc_url   doc url, config in "route" of site_config.json
        @htmls  {
                "file1_path": {
                                "title": "",
                                "desc": "",
                                "keywords": [],
                                "body": html,
                                “sidebar": "",
                                "navbar": ""
                                }
                }
        @return {
                "file1_path": {
                                "title": "",
                                "desc": "",
                                "keywords": [],
                                "body": html，
                                "sidebar": "",
                                "navbar": "",
                                "footer": ""
                                }
                }
    '''
    def generate_items(config, doc_url, level):
        li = False
        active_item = None
        have_label = "label" in config
        li_html = ""
        active = False
        if have_label and "url" in config and config["url"] != None and config["url"] != "null":
            if not config["url"].startswith("http"):
                if not config["url"].startswith("/"):
                    config["url"] = "/{}".format(config["url"])
            active = doc_url == config["url"]
            if active:
                active_item = config
            li = True
        sub_items_ul_html = ""
        if "items" in config:
            active_item = None
            sub_items_html = ""
            for item in config["items"]:
                item_html, _active_item = generate_items(item, doc_url, level + 1)
                if _active_item:
                    active_item = _active_item
                sub_items_html += item_html
            sub_items_ul_html = "<ul>{}</ul>".format(sub_items_html)
        if not li:
            li_html = '<li class="sub_items"><a>{}{}</a>{}\n'.format("{}".format(config["label"]) if have_label else "",
                                active_item["label"] if active_item else "",
                                sub_items_ul_html
                        )
        else:
            li_html = '<li class="{}"><a {} href="{}">{}</a>{}'.format(
                "active" if active else '',
                'target="{}"'.format(config["target"]) if "target" in config else "",
                config["url"], config["label"], sub_items_ul_html
            )
        html = '{}</li>\n'.format(li_html)
        return html, active_item
    
    def generate_footer_items(config, doc_url):
        left = '<ul>\n'
        middle = '<ul>\n'
        right = '<ul>\n'
        for item in config["items"]:
            html, _ = generate_items(item, doc_url, 0)
            if "position" in item:
                if item["position"] == "right":
                    right += html
                elif item["position"] == "left":
                    left += html
                else:
                    middle += html
            else:
                middle += html
        left += "</ul>\n"
        right += "</ul>\n"
        return left, middle, right

    for file, html in htmls.items():
        if not html:
            continue
        footer_left, footer_middle, footer_right = generate_footer_items(footer, doc_url)
        footer_html = '''
            <div id="footer">
                <div id="footer_left">
                    {}
                </div>
                <div id="footer_middle">
                    {}
                </div>
                <div id="footer_right">
                    {}
                </div>
            </div>'''.format(footer_left, footer_middle, footer_right)
        html["footer"] = footer_html
        htmls[file] = html
    return htmls

def construct_html(htmls, header_items_in, js_items_in, site_config, sidebar_list):
    '''
        @htmls  {
            "title": "",
            "desc": "",
            "keywords": [],
            "tags": [],
            "body": "",
            "toc": "",
            "sidebar": "",
            "navbar": ""
            "metadata": {},
            "footer": ""
        }
    '''
    files = {}
    items = list(htmls.items())
    for i, (file, html) in enumerate(items):
        if not html:
            files[file] = None
        else:
            if html["title"]:
                page_title = "{} - {}".format(html["title"], site_config["site_name"])
                article_title = html["title"]
            else:
                page_title = site_config["site_name"]
                article_title = ""
            header_items = "\n        ".join(header_items_in)
            js_items = "\n".join(js_items_in)
            tags_html = ""
            footer_html = html["footer"] if "footer" in html else ""
            for tag in html["tags"]:
                tags_html += '<li>{}</li>\n'.format(tag)
            tags_html = '<ul>{}</ul>'.format(tags_html)
            if "sidebar" in html:
                previous_item_html = ""
                next_item_html = ""
                if file in sidebar_list:
                    if sidebar_list[file]["previous"]:
                        previous_item_html = '<a href="{}"><span class="icon"></span><span>{}</span></a>'.format(sidebar_list[file]["previous"][0], sidebar_list[file]["previous"][1])
                    if sidebar_list[file]["next"]:
                        next_item_html = '<a href="{}"><span>{}</span><span class="icon"></span></a>'.format(sidebar_list[file]["next"][0], sidebar_list[file]["next"][1])
                menu_html = '''<div id="menu_wrapper">
                                    <div id="menu">
                                    </div>
                                </div>'''
                body_html = '''
        <div id="wrapper">
            {}
            {}
            <div id="article">
                <div id="content_wrapper">
                    <div id="content">
                        <div id="article_title">
                            <h1>{}</h1>
                        </div>
                        <div id="article_tags">
                            {}
                        </div>
                        <div id="article_content">
                            {}
                        </div>
                    </div>
                    <div id="previous_next">
                        <div id="previous">
                            {}
                        </div>
                        <div id="next">
                            {}
                        </div>
                    </div>
                    <div id="article_footer">
                        {}
                    </div>
                </div>
                <div id="toc">
                    <div>
                        {}
                    </div>
                </div>
            </div>
        </div>'''.format(
                        html["sidebar"],
                        menu_html,
                        article_title,
                        tags_html,
                        html["body"],
                        previous_item_html, 
                        next_item_html,
                        footer_html,
                        html["toc"] if "toc" in html else "",
                )
            else: # not "sidebar" in html
                body_html = '''
                <div id="page_wrapper">
                    <div id="page_content"><div>{}</div></div>
                    <div id="page_footer">{}</div>
                </div>'''.format(html["body"], footer_html)

            files[file] = '''<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="keywords" content="{}">
    <meta name="description" content="{}">
    <meta name="generator" content="teedoc">
    {}
    <title>{}</title>
</head>
<body>
    {}
    {}
    <a id="to_top" href="#"></a>
</body>
{}
</html>
'''.format(",".join(
                    html["keywords"]),
                    html["desc"], 
                    header_items,
                    page_title,
                    html["navbar"] if "navbar" in html else "",
                    body_html,
                    js_items
            )
    return files

def update_html_abs_path(file_htmls, root_path):
    def re_del(c):
        content = c[0]
        if content.startswith("src"):
            if content[5] == "/" and content[6] != "/":
                content = "{}{}{}".format(content[:5], root_path[:-1], content[5:])
        elif content.startswith("href"):
            if content[6] == "/" and content[7] != "/": # href="/static/..."
                content = "{}{}{}".format(content[:6], root_path[:-1], content[6:])
        else:
            if content[4] != "/" and content[5] == "/" and content[6] != "/": # url("/static/...")
                content = "{}{}{}".format(content[:5], root_path[:-1], content[5:])
            elif content[4] == "/" and content[5] != "/": # url(/static/...)
                content = "{}{}{}".format(content[:4], root_path[:-1], content[4:])
        return content

    for path in file_htmls:
        if not file_htmls[path]:
            continue
        file_htmls[path] = re.sub(r'href=".*?"', re_del, file_htmls[path])
        file_htmls[path] = re.sub(r'src=".*?"', re_del, file_htmls[path])
        file_htmls[path] = re.sub(r'url(.*?)', re_del, file_htmls[path])
    return file_htmls

def parse(plugin_func, routes, site_config, doc_src_path, log, out_dir, plugins_objs, header_items, js_items, sidebar, allow_no_navbar):
    site_root_url = site_config["site_root_url"]
    global g_is_error
    g_is_error = False
    if not site_root_url.endswith("/"):
        site_root_url = "{}/".format(site_root_url)
    for url, dir in routes.items():
        dir = os.path.abspath(os.path.join(doc_src_path, dir)).replace("\\", "/")
        log.i("parse doc: {}, url:{}".format(dir, url))
        # get sidebar config
        if sidebar:
            try:
                sidebar = get_sidebar(dir)
            except Exception as e:
                log.e("parse sidebar.json fail: {}".format(e))
                return False
        try:
            navbar = get_navbar(dir)
        except Exception as e:
            if not allow_no_navbar:
                log.e("parse config.json navbar fail: {}".format(e))
                return False
            navbar = None
        try:
            footer = get_footer(dir)
        except Exception as e:
            footer = None
        all_files = get_files(dir)
        def on_err():
            global g_is_error
            g_is_error = True
        def is_err():
            global g_is_error
            return g_is_error
        

        def generate(files, url, dir, plugin_func, routes, site_config, doc_src_path, log, out_dir, plugins_objs, header_items, js_items, sidebar, allow_no_navbar):
            try:
                # call plugins to parse files
                result_htmls = None
                for plugin in plugins_objs:
                    # parse file content
                    result = plugin.__getattribute__(plugin_func)(files)
                    if result:
                        if not result['ok']:
                            log.e("plugin <{}> {} error: {}".format(plugin.name, plugin_func, result['msg']))
                            on_err()
                            return False
                        else:
                            result_htmls = result['htmls'] # will cover the before
                    if is_err():
                        return False
                if not result_htmls:
                    log.e("parse files error")
                    on_err()
                    return False
                htmls = result_htmls
                # generate sidebar to html
                if sidebar:
                    sidebar_list = get_sidebar_list(sidebar, dir, url)
                    htmls = generate_sidebar_html(htmls, sidebar, dir, url, sidebar["title"] if "title" in sidebar else "")
                else:
                    sidebar_list = {}
                if is_err():
                    return False
                # generate navbar to html
                if navbar:
                    htmls = generate_navbar_html(htmls, navbar, dir, url, plugins_objs)
                if footer:
                    htmls = generate_footer_html(htmls, footer, dir, url, plugins_objs)
                if is_err():
                    return False
                # consturct html page
                htmls = construct_html(htmls, header_items, js_items, site_config, sidebar_list)
                if is_err():
                    return False
                # check abspath
                if site_root_url != "/":
                    htmls = update_html_abs_path(htmls, site_root_url)
                if is_err():
                    return False
                # write to file
                if url.startswith("/"):
                    url = url[1:]
                out_path = os.path.join(out_dir, url)
                in_path  = os.path.join(doc_src_path, dir)
                ok, msg = write_to_file(htmls, in_path, out_path)
                if not ok:
                    log.e("write files error: {}".format(msg))
                    on_err()
                    return False
                if is_err():
                    return False
            except Exception as e:
                log.e("generate html fail: {}".format(e))
                on_err()
                raise e
                return False
            log.i("generate ok")
            return True

        max_threads_num = multiprocessing.cpu_count()
        if len(all_files) > 10:
            all_files = split_list(all_files, max_threads_num)
            ts = []
            for files in all_files:
                t = threading.Thread(target=generate, args=(files, url, dir, plugin_func, routes, site_config, doc_src_path, log, out_dir, plugins_objs, header_items, js_items, sidebar, allow_no_navbar))
                t.setDaemon(True)
                t.start()
                ts.append(t)
            for t in ts:
                t.join()
                # log.i("{} generate ok".format(t.name))
        else:
            return generate(all_files, url, dir, plugin_func, routes, site_config, doc_src_path, log, out_dir, plugins_objs, header_items, js_items, sidebar, allow_no_navbar)
    return True

def build(doc_src_path, plugins_objs, site_config, out_dir, log):
    '''
        "route": {
            "docs": {
                "/get_started/zh": "docs/get_started/zh",
                "/get_started/en": "docs/get_started/en",
                "/develop/zh": "docs/develop/zh",
                "/develop/en": "docs/develop/en"
            },
            "pages": {
                "/": "pages/index/zh",
                "/en": "pages/index/en"
            },
            "/blog": "blog"
        }
    '''

    # ---start---
    # get html header item from plugins
    header_items = []
    js_items = []
    for plugin in plugins_objs:
        items = plugin.on_add_html_header_items()
        _js_items = plugin.on_add_html_js_items()
        if type(items) != list or type(_js_items) != list:
            log.e("plugin <{}> error, on_add_html_header_items should return list type".format(plugin.name))
            return False
        if items:
            header_items.extend(items)
        if _js_items:
            js_items.extend(_js_items)
    # parse all docs
    routes = site_config["route"]["docs"]
    if not parse("on_parse_files", routes, site_config, doc_src_path, log, out_dir, plugins_objs, header_items, js_items, sidebar=True, allow_no_navbar=False):
        return False

    # parse all pages
    routes = site_config["route"]["pages"]
    if not parse("on_parse_files", routes, site_config, doc_src_path, log, out_dir, plugins_objs, header_items, js_items, sidebar=False, allow_no_navbar=True):
        return False
    # parse all blogs
    # copy assets
    assets = site_config["route"]["assets"]
    for target_dir, from_dir in assets.items(): 
        in_path  = os.path.join(doc_src_path, from_dir)
        if target_dir.startswith("/"):
            target_dir = target_dir[1:]
        out_path = os.path.join(out_dir, target_dir)
        if not copy_dir(in_path, out_path):
            return False
    # copy files from pulgins
    for plugin in plugins_objs:
        files = plugin.on_copy_files()
        for dst,src in files.items():
            if dst.startswith("/"):
                dst = dst[1:]
            dst = os.path.join(out_dir, dst)
            if not os.path.isabs(src):
                log.e("plugin <{}> on_copy_files error, file path {} must be abspath".format(plugin.name, src))
            if not copy_file(src, dst):
                return False
    return True


def main():
    log = Logger(level="d")
    parser = argparse.ArgumentParser(description="teedoc, a doc generator, generate html from markdown and jupyter notebook")
    parser.add_argument("-p", "--path", default=".", help="doc source root path" )
    parser.add_argument("command", choices=["install", "build", "serve"])
    args = parser.parse_args()
    # doc source code root path
    doc_src_path = os.path.abspath(args.path)
    # parse site config
    ok, site_config = parse_site_config(doc_src_path)
    if not ok:
        log.e(site_config)
        return 1
    # out_dir
    if site_config["site_root_url"] != "/":
        serve_dir = os.path.join(doc_src_path, "out")
        out_dir = os.path.join(serve_dir, site_config["site_root_url"][1:])
    else:
        serve_dir = os.path.join(doc_src_path, "out")
        out_dir = serve_dir
    # execute command
    if args.command == "install":
        log.i("install, source doc root path: {}".format(doc_src_path))
        log.i("plugins: {}".format(list(site_config["plugins"].keys())))
        curr_path = os.getcwd()
        for plugin, info in site_config['plugins'].items():
            path = info['from']
            # install from pypi.org
            if not path or path.lower() == "pypi":
                log.i("install plugin <{}> from pypi.org".format(plugin))
                cmd = [site_config["executable"]["pip"], "install", "--upgrade", plugin]
                p = subprocess.Popen(cmd, shell=False)
                p.communicate()
                if p.returncode != 0:
                    log.e("install <{}> fail".format(plugin))
                    return 1
                log.i("install <{}> complete".format(plugin))
            # install from git like: git+https://github.com/Neutree/COMTool.git#egg=comtool
            elif path.startswith("svn") or path.startswith("git"):
                log.i("install plugin <{}> from {}".format(plugin, path))
                cmd = [site_config["executable"]["pip"], "install", "-e", path]
                log.i("install <{}> by pip: {}".format(plugin, " ".join(cmd)))
                p = subprocess.Popen(cmd, shell=False)
                p.communicate()
                if p.returncode != 0:
                    log.e("install <{}> fail".format(plugin))
                    return 1
                log.i("install <{}> complete".format(plugin))
            # install from local file system
            else:
                if not os.path.isabs(path):
                    path = os.path.abspath(os.path.join(doc_src_path, path))
                if not os.path.exists(path):
                    log.e("{} not found".format(path))
                    return 1
                os.chdir(path)
                cmd = [site_config["executable"]["pip"], "install", "."]
                log.i("plugin path: {}".format(path))
                log.i("install <{}> by pip: {}".format(plugin, " ".join(cmd)))
                p = subprocess.Popen(cmd, shell=False)
                p.communicate()
                if p.returncode != 0:
                    log.e("install <{}> fail".format(plugin))
                    return 1
                log.i("install <{}> complete".format(plugin))
        os.chdir(curr_path)
        log.i("all plugins install complete")
    elif args.command == "build":
        # init plugins
        plugins = list(site_config['plugins'].keys())
        plugins_objs = []
        log.i("plugins: {}".format(plugins))
        for plugin, info in site_config['plugins'].items():
            try:
                plugin_config = info['config']
            except Exception:
                plugin_config = {}
            # import plugin from local source code
            path = info["from"]
            if not os.path.isabs(path):
                path = os.path.abspath(os.path.join(doc_src_path, path))
            if os.path.exists(path):
                sys.path.insert(0, path)
            plugin_import_name = plugin.replace("-", "_")
            module = __import__(plugin_import_name)
            plugin_obj = module.Plugin(doc_src_path=doc_src_path, config=plugin_config, site_config=site_config, logger=log)
            plugins_objs.append(plugin_obj)
        # parse files
        if not build(doc_src_path, plugins_objs, site_config=site_config, out_dir=out_dir, log=log):
            return 1
    elif args.command == "serve":
        from http.server import HTTPServer, BaseHTTPRequestHandler

        host = ('0.0.0.0', 2333)
        
        class On_Resquest(BaseHTTPRequestHandler):
            def do_GET(self):
                file_path = self.path[1:]
                if not file_path:
                    file_path = "index.html"
                file_path = os.path.join(serve_dir, file_path)
                if not os.path.exists(file_path) or not os.path.isfile(file_path):
                    file_path = os.path.join(file_path, "index.html")
                if not os.path.exists(file_path):
                    file_path = os.path.join(out_dir, "404.html")
                    self.send_response(404)
                else:
                    self.send_response(200)
                if not os.path.exists(file_path):
                    content = b"page not found"
                    content_type = "text/html"
                else:
                    with open(file_path, "rb") as f:
                        content = f.read()
                    content_type = get_content_type_by_path(file_path)
                self.send_header('Content-type', content_type)
                self.end_headers()
                self.wfile.write(content)
                # print(self.address_string())
                # print(self.request)
 
        server = HTTPServer(host, On_Resquest)
        log.i("root dir: {}".format(serve_dir))
        log.i("Starting server at {}:{} ....".format(host[0], host[1]))
        server.serve_forever()
    else:
        log.e("command error")
        return 1
    return 0



if __name__ == "__main__":
    ret = main()
    sys.exit(ret)

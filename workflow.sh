#!/bin/bash
# 豆瓣多功能爬虫 - 完整工作流程脚本
#
# 特性:
# - 自动检测并激活虚拟环境 (.venv)
# - 完整端到端流程：搜索 -> 添加 -> 上传
#
# 用法:
#   ./workflow.sh search "专辑名"              # 搜索专辑
#   ./workflow.sh add <URL>                   # 添加专辑到本地
#   ./workflow.sh list                         # 列出本地专辑
#   ./workflow.sh show <album_id>             # 显示专辑详情
#   ./workflow.sh upload <album_id>           # 上传到豆瓣
#   ./workflow.sh full "专辑名"               # 完整流程：搜索 -> 添加 -> 上传
#   ./workflow.sh login                        # 登录豆瓣

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 项目路径
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 初始化 Python 命令
PYTHON_CMD=""
init_python() {
    if [ -z "$PYTHON_CMD" ]; then
        # 优先使用虚拟环境
        for venv in ".venv" "venv" "env"; do
            if [ -x "$PROJECT_DIR/$venv/bin/python" ]; then
                PYTHON_CMD="$PROJECT_DIR/$venv/bin/python"
                break
            fi
        done
        # 回退到系统 Python
        if [ -z "$PYTHON_CMD" ]; then
            PYTHON_CMD="python"
        fi
    fi
}

# 执行 Python 命令
run_python() {
    init_python
    $PYTHON_CMD "$@"
}

# 打印分隔线
print_divider() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
}

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 显示帮助
show_help() {
    echo -e "${CYAN}豆瓣多功能爬虫${NC} - 端到端工作流程脚本"
    echo ""
    echo "用法: $0 <命令> [参数]"
    echo ""
    echo "命令:"
    echo "  full <关键词>     交互式搜索→选择→添加→上传 (推荐)"
    echo "  search <关键词>   搜索专辑"
    echo "  add <URL>        添加专辑"
    echo "  list             列出本地专辑"
    echo "  show <ID>        显示专辑详情"
    echo "  upload <ID>       上传到豆瓣"
    echo "  clear            清空所有数据"
    echo "  login            登录豆瓣"
    echo "  check            检查环境"
    echo ""
    echo "示例:"
    echo "  $0 full \"Immanuel Wilkins Village Vanguard\""
    echo "  $0 show xmahll"
    echo "  $0 upload xmahll"
}

# 检查环境
cmd_check() {
    print_divider
    echo -e "${CYAN}环境检查${NC}"
    print_divider
    echo ""
    log_info "Python 版本:"
    run_python --version
    echo ""
    log_info "检查依赖包..."
    for pkg in click httpx beautifulsoup4 playwright rich pyyaml pydantic; do
        if run_python -c "import $pkg" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $pkg"
        else
            echo -e "  ${RED}✗${NC} $pkg (未安装)"
        fi
    done
    echo ""
    log_info "检查数据目录..."
    for dir in data/albums data/images data/cookies; do
        if [ -d "$dir" ]; then
            echo -e "  ${GREEN}✓${NC} $dir"
        else
            echo -e "  ${YELLOW}!${NC} $dir (将自动创建)"
            mkdir -p "$dir"
        fi
    done
    echo ""
    log_info "检查豆瓣登录..."
    if [ -f "data/cookies/douban.json" ]; then
        echo -e "  ${GREEN}✓${NC} 已登录豆瓣"
    else
        echo -e "  ${YELLOW}!${NC} 未登录豆瓣，运行 '$0 login' 登录"
    fi
}

# 搜索
cmd_search() {
    local query="$*"
    if [ -z "$query" ]; then
        log_error "请提供搜索关键词"
        exit 1
    fi
    print_divider
    echo -e "${CYAN}搜索专辑: $query${NC}"
    print_divider
    echo ""
    run_python main.py search "$query" -s musicbrainz -l 5
    echo ""
    run_python main.py search "$query" -s applemusic -l 3
}

# 添加
cmd_add() {
    local arg="$1"
    if [ -z "$arg" ]; then
        log_error "请提供 URL"
        echo "  $0 add \"https://music.apple.com/cn/album/...\""
        exit 1
    fi
    print_divider
    echo -e "${CYAN}添加专辑${NC}"
    print_divider
    echo ""
    if [[ "$arg" == http* ]]; then
        log_info "从 URL 添加: $arg"
        run_python main.py add --url "$arg"
    else
        run_python main.py add "$@"
    fi
}

# 列出
cmd_list() {
    print_divider
    echo -e "${CYAN}本地专辑${NC}"
    print_divider
    echo ""
    run_python main.py list
}

# 显示
cmd_show() {
    local album_id="$1"
    if [ -z "$album_id" ]; then
        log_error "请提供 album_id"
        exit 1
    fi
    print_divider
    echo -e "${CYAN}专辑详情${NC}"
    print_divider
    echo ""
    run_python main.py show "$album_id"
}

# 上传
cmd_upload() {
    local album_id="$1"
    if [ -z "$album_id" ]; then
        log_error "请提供 album_id"
        echo "  使用 $0 list 查看所有专辑"
        exit 1
    fi
    # 检查登录
    if [ ! -f "data/cookies/douban.json" ]; then
        log_warn "未登录豆瓣，正在打开浏览器..."
        echo ""
        cmd_login
        echo ""
        read -p "登录完成后，按回车继续: "
    fi
    print_divider
    echo -e "${CYAN}上传到豆瓣${NC}"
    print_divider
    echo ""
    run_python main.py upload "$album_id"
}

# 登录
cmd_login() {
    print_divider
    echo -e "${CYAN}豆瓣登录${NC}"
    print_divider
    echo ""
    log_info "打开浏览器，请在浏览器中手动登录豆瓣"
    echo ""
    run_python main.py login
}

# 统计
cmd_stats() {
    print_divider
    echo -e "${CYAN}统计信息${NC}"
    print_divider
    echo ""
    run_python main.py stats
}

# 清空数据
cmd_clear() {
    local force_flag=""
    if [ "$1" = "-f" ] || [ "$1" = "--force" ]; then
        force_flag="--force"
    fi
    print_divider
    echo -e "${RED}清空所有数据${NC}"
    print_divider
    echo ""
    if [ -z "$force_flag" ]; then
        log_warn "此操作将删除所有本地专辑数据！"
        echo ""
    fi
    run_python main.py clear $force_flag
}

# 完整流程 - 使用交互式选择
cmd_full() {
    local query="$*"
    if [ -z "$query" ]; then
        log_error "请提供专辑关键词"
        exit 1
    fi
    print_divider
    echo -e "${CYAN}完整工作流程 - 交互模式${NC}"
    echo -e "${CYAN}专辑: $query${NC}"
    print_divider
    echo ""
    log_info "启动交互式搜索和添加..."
    echo ""
    echo -e "${YELLOW}💡 提示: 推荐选择 Apple Music 来源的专辑，曲目信息最完整${NC}"
    echo ""
    run_python main.py interactive "$query"
    print_divider
    log_success "工作流程完成!"
    print_divider
}

# 主逻辑
case "$1" in
    search) shift; cmd_search "$@";;
    add) shift; cmd_add "$@";;
    list|ls) cmd_list;;
    show|info) shift; cmd_show "$@";;
    upload|push) shift; cmd_upload "$@";;
    full|pipeline) shift; cmd_full "$@";;
    login|auth) cmd_login;;
    stats|stat) cmd_stats;;
    clear|clean) shift; cmd_clear "$@";;
    check|env|status) cmd_check;;
    help|--help|-h) show_help;;
    *) show_help;;
esac

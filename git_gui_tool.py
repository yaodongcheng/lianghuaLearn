#!/usr/bin/env python3
"""
Git 图形化快捷工具 - 极简弹窗版
"""

import tkinter as tk
from tkinter import messagebox, simpledialog, scrolledtext
import subprocess
import sys
import os

# 切换到项目目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Git 路径（根据您的系统调整）
GIT_PATH = r"D:\Git\cmd\git.exe"


def run_git(cmd):
    """运行 git 命令"""
    full_cmd = cmd.replace('git ', f'"{GIT_PATH}" ', 1)
    result = subprocess.run(full_cmd, shell=True, capture_output=True)
    stdout = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
    stderr = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
    return result.returncode == 0, stdout, stderr


def get_status():
    """获取当前状态"""
    success, stdout, _ = run_git("git status --porcelain")
    if success:
        return stdout.strip()
    return ""


def get_branch():
    """获取当前分支"""
    success, stdout, _ = run_git("git branch --show-current")
    if success:
        return stdout.strip()
    return "main"


def commit(push_after=False):
    """提交更改"""
    status = get_status()
    if not status:
        messagebox.showinfo("提示", "没有需要提交的更改")
        return False
    
    # 添加所有更改
    run_git("git add -A")
    
    # 询问提交信息
    msg = simpledialog.askstring("提交", "输入提交信息:", initialvalue="更新代码")
    if not msg:
        return False
    
    success, stdout, stderr = run_git(f'git commit -m "{msg}"')
    if success:
        if push_after:
            return push()
        else:
            messagebox.showinfo("成功", "本地提交成功！\n记得点击'推送'上传到 GitHub")
            return True
    else:
        messagebox.showerror("错误", f"提交失败:\n{stderr}")
        return False


def push():
    """推送到远程"""
    branch = get_branch()
    success, stdout, stderr = run_git(f"git push origin {branch}")
    if success:
        messagebox.showinfo("成功", f"已推送到 GitHub！\n分支: {branch}")
        return True
    else:
        # 检查是否需要设置上游分支
        if "no upstream branch" in stderr.lower():
            success, stdout, stderr = run_git(f"git push -u origin {branch}")
            if success:
                messagebox.showinfo("成功", f"已推送到 GitHub！\n分支: {branch}")
                return True
        messagebox.showerror("错误", f"推送失败:\n{stderr}")
        return False


def commit_and_push():
    """提交并推送"""
    if commit(push_after=True):
        update_status_label()


def pull():
    """从远程拉取"""
    branch = get_branch()
    success, stdout, stderr = run_git(f"git pull origin {branch}")
    if success:
        messagebox.showinfo("成功", f"已从 GitHub 拉取最新代码！\n分支: {branch}")
        update_status_label()
        return True
    else:
        messagebox.showerror("错误", f"拉取失败:\n{stderr}")
        return False


def show_log():
    """显示提交历史"""
    success, stdout, _ = run_git("git log --oneline -20 --graph")
    if success:
        # 创建新窗口显示日志
        log_window = tk.Toplevel()
        log_window.title("提交历史")
        log_window.geometry("500x400")
        
        text_area = scrolledtext.ScrolledText(log_window, wrap=tk.WORD, font=("Consolas", 10))
        text_area.pack(expand=True, fill='both', padx=10, pady=10)
        text_area.insert(tk.END, stdout)
        text_area.config(state=tk.DISABLED)
        
        tk.Button(log_window, text="关闭", command=log_window.destroy).pack(pady=5)
    else:
        messagebox.showerror("错误", "无法获取提交历史")


def reset():
    """回退版本"""
    # 获取最近提交
    success, stdout, _ = run_git("git log --oneline -10")
    if not success:
        messagebox.showerror("错误", "无法获取提交历史")
        return
    
    # 显示提交历史并询问
    msg = "最近提交:\n\n" + stdout + "\n\n输入要回退的版本号 (前7位即可):"
    commit_hash = simpledialog.askstring("回退版本", msg)
    
    if not commit_hash:
        return
    
    if not messagebox.askyesno("确认", f"确定要回退到 {commit_hash}?\n这将丢失当前未提交的更改！"):
        return
    
    success, _, stderr = run_git(f"git reset --hard {commit_hash}")
    if success:
        # 强制推送到远程
        branch = get_branch()
        success_push, _, stderr_push = run_git(f"git push origin {branch} --force")
        if success_push:
            messagebox.showinfo("成功", "回退成功并已强制推送到 GitHub！")
        else:
            messagebox.showwarning("警告", f"本地回退成功，但推送失败:\n{stderr_push}")
        update_status_label()
    else:
        messagebox.showerror("错误", f"回退失败:\n{stderr}")


def update_status_label():
    """更新状态标签"""
    status_text = get_status()
    branch = get_branch()
    if status_text:
        status_label.config(text=f"分支: {branch} | 有未提交的更改", fg="orange")
    else:
        status_label.config(text=f"分支: {branch} | 工作区干净", fg="green")


def main():
    """主界面"""
    global status_label
    
    root = tk.Tk()
    root.title("Git 快捷工具 - lianghuaLearn")
    root.geometry("350x400")
    root.resizable(False, False)
    
    # 居中显示
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - 175
    y = (root.winfo_screenheight() // 2) - 200
    root.geometry(f'+{x}+{y}')
    
    # 标题
    tk.Label(root, text="🚀 Git 快捷工具", font=("Microsoft YaHei", 18, "bold"), pady=15).pack()
    tk.Label(root, text="项目: lianghuaLearn", font=("Microsoft YaHei", 10), fg="gray").pack()
    
    # 按钮框架
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=20)
    
    btn_width = 25
    btn_height = 2
    
    # 提交并推送按钮
    tk.Button(btn_frame, text="📤 提交并推送", width=btn_width, height=btn_height,
              font=("Microsoft YaHei", 11),
              bg="#2196F3", fg="white",
              command=commit_and_push).pack(pady=5)
    
    # 拉取代码按钮
    tk.Button(btn_frame, text="📥 拉取代码", width=btn_width, height=btn_height,
              font=("Microsoft YaHei", 11),
              command=lambda: [pull(), update_status_label()]).pack(pady=5)
    
    # 查看历史按钮
    tk.Button(btn_frame, text="📜 查看提交历史", width=btn_width, height=btn_height,
              font=("Microsoft YaHei", 11),
              command=show_log).pack(pady=5)
    
    # 回退版本按钮
    tk.Button(btn_frame, text="⏪ 回退版本", width=btn_width, height=btn_height,
              font=("Microsoft YaHei", 11), bg="#f44336", fg="white",
              command=lambda: [reset(), update_status_label()]).pack(pady=5)
    
    # 刷新状态按钮
    tk.Button(btn_frame, text="🔄 刷新状态", width=btn_width, height=btn_height,
              font=("Microsoft YaHei", 10),
              command=update_status_label).pack(pady=5)
    
    # 状态显示
    status_frame = tk.Frame(root, bd=1, relief=tk.SUNKEN)
    status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
    
    status_label = tk.Label(status_frame, text="正在检查状态...", font=("Microsoft YaHei", 9))
    status_label.pack(pady=5)
    
    # 初始化状态
    update_status_label()
    
    root.mainloop()


if __name__ == "__main__":
    main()

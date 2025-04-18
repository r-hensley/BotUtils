import asyncio
import importlib
import json
import logging
import os
import re
import shutil
import sys
import traceback
import unittest

import emoji

from copy import deepcopy
from datetime import datetime
from typing import Optional, Union, Callable

import aiohttp
import discord
from discord.ext import commands

dir_path = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.realpath(__file__)))))

# here = sys.modules[__name__]
# here.bot = None
# here.loop = None

class Here:
    def __init__(self):
        if self.__class__.__name__ == "Rai":
            # noinspection PyUnresolvedReferences, PyPackageRequirements
            from Rai import Rai as MyBot
        elif self.__class__.__name__ == "Modbot":
            # noinspection PyUnresolvedReferences, PyPackageRequirements
            from Modbot import Modbot as MyBot
        else:
            # noinspection PyPep8Naming
            MyBot = commands.Bot
        self.bot: Optional[MyBot] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

here = Here()

BANS_CHANNEL_ID = 329576845949534208
SP_SERV_ID = 243838819743432704
CH_SERV_ID = 266695661670367232
JP_SERVER_ID = 189571157446492161
FEDE_GUILD = discord.Object(941155953682821201)
RY_SERV = discord.Object(275146036178059265)

SP_SERV_GUILD = discord.Object(SP_SERV_ID)
JP_SERV_GUILD = discord.Object(JP_SERVER_ID)

_lock = asyncio.Lock()


def setup(bot, loop):
    """This command is run in the setup_hook function in Rai.py"""
    global here
    if here.bot is None:
        here.bot = bot
    else:
        pass

    if here.loop is None:
        here.loop = loop
    else:
        pass

    try:
        test_module = importlib.import_module("cogs.utils.BotUtils.tests.test_bot_utils")
    except ModuleNotFoundError:
        print("Skipping BotUtils test suite")
    else:
        test_module = importlib.reload(test_module)
        suite = unittest.TestLoader().loadTestsFromModule(test_module)
        test_runner = unittest.TextTestRunner(verbosity=1)
        # Verbosity:
        # 0 (quiet): you just get the total numbers of tests executed and the global result
        # 1 (default): you get the same plus a dot for every successful test or a F for every failure
        # 2 (verbose): you get the help string of every test and the result
        test_runner.run(suite)


# credit: https://gist.github.com/dperini/729294
_url = re.compile(
    r"""
            # protocol identifier
            (?:https?|ftp)://
            # user:pass authentication
            (?:\S+(?::\S*)?@)?
            (?:
              # IP address exclusion
              # private & local networks
              (?!(?:10|127)(?:\.\d{1,3}){3})
              (?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})
              (?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})
              # IP address dotted notation octets
              # excludes loopback network 0.0.0.0
              # excludes reserved space >= 224.0.0.0
              # excludes network & broacast addresses
              # (first & last IP address of each class)
              (?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])
              (?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}
              \.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4])
            |
              # host name
              (?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+
              # domain name
              (?:\.(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)*
              # TLD identifier
              \.[a-z\u00a1-\uffff]{2,}
              # TLD may end with dot
              \.?
            )
            # port number
            (?::\d{2,5})?
            # resource path
            (?:[/?#]\S*)?
        """, re.VERBOSE | re.I)

_emoji = re.compile(r'<a?(:[A-Za-z0-9_]+:|#|@|@&)!?[0-9]{17,20}>')


def green_embed(text):
    return discord.Embed(description=text, color=0x23ddf1)


def red_embed(text):
    return discord.Embed(description=text, color=0x9C1313)


def grey_embed(text):
    return discord.Embed(description=text, color=0x848A84)


async def safe_send(destination: Union[commands.Context, discord.abc.Messageable],
                    content='', *,
                    embed: discord.Embed = None,
                    embeds: list[discord.Embed] = None,
                    delete_after: float = None,
                    file: discord.File = None,
                    view: discord.ui.View = None):
    """A command to be clearer about permission errors when sending messages"""
    if not content and not embed and not file:
        if isinstance(destination, str):
            raise SyntaxError("You maybe forgot to state a destination in the safe_send() function")
        elif isinstance(destination, discord.abc.Messageable):
            raise SyntaxError("The content you tried to send in the safe_send() function was None")
        else:
            raise SyntaxError("There was an error parsing the arguments of the safe_send() function")

    try:
        if content is not None:
            content = str(content)
    except TypeError:
        raise TypeError("You tried to pass something in as content to safe_send that can't be converted to a string")
    
    if len(content or '') > 2000:
        raise ValueError(f"Content to send is too long: {len(content)} characters (2000 max)")

    perms_set = perms = False
    if isinstance(destination, commands.Context):
        if destination.guild:
            perms = destination.channel.permissions_for(destination.guild.me)
            perms_set = True
    elif isinstance(destination, discord.TextChannel):
        perms = destination.permissions_for(destination.guild.me)
        perms_set = True
    if not destination:
        return

    if perms_set:
        if embed and not perms.embed_links and perms.send_messages:
            await destination.send("I lack permission to upload embeds here.")
            return

    try:
        if isinstance(destination, discord.User):
            if not destination.dm_channel:
                await destination.create_dm()
                
        if embeds and embed:
            raise ValueError("You can't pass both embed and embeds to safe_send")
        elif embed:
            embeds = [embed]
        return await destination.send(content, embeds=embeds, delete_after=delete_after, file=file, view=view)

    except discord.Forbidden:
        if isinstance(destination, commands.Context):
            ctx = destination  # shorter and more accurate name
            msg_content = f"Rai tried to send a message to #{ctx.channel.name} but lacked permissions to do so " \
                          f"(either messages or embeds)."

            try:
                await safe_send(ctx.author, msg_content)
            except (discord.Forbidden, discord.HTTPException):
                pass  # pass ok because this is already assuming discord.Forbidden and we are still failing to send

        raise

    # discord.errors.HTTPException: 400 Bad Request (error code: 240000): Message blocked by harmful links filter
    except discord.HTTPException as e:
        if e.code == 240000:
            return await destination.send("Discord blocked me from sending that message because it" 
                                          "contains a harmful link.")
        else:
            raise


async def safe_reply(message: Union[discord.Message, commands.Context], content: str = None, **kwargs):
    try:
        msg = await message.reply(content, **kwargs)
    except discord.HTTPException:
        msg = await safe_send(message.channel, content, **kwargs)
    return msg


async def member_converter(ctx: commands.Context, user_in: Union[str, int]) -> Optional[discord.Member]:
    # check for an ID
    if isinstance(user_in, int):
        user_in = str(user_in)
    user_id = re.findall(r"(^<@!?\d{17,22}>$|^\d{17,22}$)", str(user_in))
    if user_id:
        user_id = user_id[0].replace('<@', '').replace('>', '').replace('!', '')
        member = ctx.guild.get_member(int(user_id))
        return member

    # # check for an exact name
    # member = ctx.guild.get_member_named(user_in)
    # if member:
    #     return member

    # try the beginning of the name
    import cogs.utils.helper_functions as hf
    top_members = hf.get_top_server_members_activity(ctx.guild)
    top_members_names = [
        (member.name.casefold(),
         member.nick.casefold() if member.nick else '',
         member.display_name.casefold() if member.display_name else '',
         member)
        for member in top_members]
    remaining_member_list = [
        (member.name.casefold(),
         member.nick.casefold() if member.nick else '',
         member.display_name.casefold() if member.display_name else '',
         member)
        for member in ctx.guild.members]
    member_list = top_members_names + remaining_member_list  # the order is important
    user_in = user_in.casefold()
    for member in member_list:
        if member[0].startswith(user_in):
            return member[3]
        if member[1].startswith(user_in):
            return member[3]
        if member[2].startswith(user_in):
            return member[3]

    # is it anywhere in the name
    for member in member_list:
        if user_in in member[0]:
            return member[3]
        if user_in in member[1]:
            return member[3]
        if user_in in member[2]:
            return member[3]

    return None


async def user_converter(ctx: commands.Context, user_in: Union[str, int]) -> Union[None, discord.User, discord.Member]:
    """Doesn't convert to a member first, try doing utils.member_converter() before utils.user_converter()."""
    if isinstance(user_in, int):
        user_in = str(user_in)
    try:
        user_id = int(re.search(r"<?@?!?(\d{17,22})>?", user_in).group(1))
    except (AttributeError, ValueError):
        return None
    else:
        try:
            user = await ctx.bot.fetch_user(user_id)
            return user
        except (discord.NotFound, discord.HTTPException):
            return None


def _predump_json(name: str = 'db'):
    if name == 'db':
        db_copy = deepcopy(here.bot.db)
    elif name == 'stats':
        db_copy = deepcopy(here.bot.stats)
    elif name == 'message_queue':
        db_copy = deepcopy(here.bot.message_queue.to_dict_list())
    else:
        raise ValueError("name must be 'db' or 'stats' or 'message_queue'")
        
    if not os.path.exists(f'{dir_path}/{name}_2.json'):
        # if backup files don't exist yet, create them
        shutil.copy(f'{dir_path}/{name}.json', f'{dir_path}/{name}_2.json')
        shutil.copy(f'{dir_path}/{name}_2.json', f'{dir_path}/{name}_3.json')
        shutil.copy(f'{dir_path}/{name}_3.json', f'{dir_path}/{name}_4.json')
    else:
        # make incremental backups of db.json
        shutil.copy(f'{dir_path}/{name}_3.json', f'{dir_path}/{name}_4.json')
        shutil.copy(f'{dir_path}/{name}_2.json', f'{dir_path}/{name}_3.json')
        shutil.copy(f'{dir_path}/{name}.json', f'{dir_path}/{name}_2.json')

    with open(f'{dir_path}/{name}_temp.json', 'w') as write_file:
        # noinspection PyTypeChecker
        json.dump(db_copy, write_file, indent=4)
    shutil.copy(f'{dir_path}/{name}_temp.json', f'{dir_path}/{name}.json')


async def dump_json(name):
    # Wait up to five minutes for the lock to be released
    for _ in range(5):
        if _lock.locked():
            logging.info("In dump_json, _lock is already locked, waiting 60s")
            await asyncio.sleep(60)
        if not _lock.locked():
            break

    # if still locked
    if _lock.locked():
        raise Exception("Attempted to call dump_json while _lock was locked; waiting five minutes didn't help.")

    async with _lock:
        try:
            await here.loop.run_in_executor(None, _predump_json, name)
        except RuntimeError:
            print("Restarting dump_json on a RuntimeError")
            await here.loop.run_in_executor(None, _predump_json, name)


def load_db(bot, name: str):
    """
    Load data from a JSON file and update the specified attribute of the bot object.

    Args:
        bot: The bot object whose attribute needs to be updated.
        name (str): The name of the attribute to update. Must be 'db' or 'stats'.

    Raises:
        ValueError: If name is not 'db' or 'stats'.
        FileNotFoundError: If the specified JSON file does not exist.
        PermissionError: If the program does not have permission to open the JSON file.
        json.decoder.JSONDecodeError: If there is an error decoding JSON data from the file.
    """
    if name not in ['db', 'stats', 'message_queue']:
        raise ValueError("name must be 'db' or 'stats' or 'message_queue'")
    try:
        with open(f"{dir_path}/{name}.json", "r") as read_file1:
            read_file1.seek(0)
            data = json.load(read_file1)

    except FileNotFoundError:
        logging.warning(f"File {name}.json not found.")
        setattr(bot, name, {})
    except PermissionError:
        logging.error(f"Permission denied when opening {name}.json.")
        raise
    except json.decoder.JSONDecodeError as e:
        if e.msg == "Expecting value":
            logging.warning(f"No data detected in {name}.json")
            setattr(bot, name, {})
        else:
            logging.error(f"Error decoding JSON in {name}.json: {e}")
            raise
    
    else:
        if name == 'message_queue':
            # noinspection PyUnresolvedReferences
            from ..helper_functions import MessageQueue
            bot.message_queue = MessageQueue.from_dict(data)
        else:
            setattr(bot, name, data)
            


def rem_emoji_url(msg: Union[discord.Message, str]) -> str:
    if isinstance(msg, discord.Message):
        msg_content = msg.content
    else:
        assert isinstance(msg, str), f"msg is not a string or discord.Message: {msg} ({type(msg)})"
        msg_content = msg
    new_msg = _emoji.sub('', _url.sub('', msg_content))
    for char in msg_content:
        if emoji.is_emoji(char):
            new_msg = new_msg.replace(char, '').replace('  ', '')
    return new_msg


def jpenratio(msg_content: str) -> Optional[float]:
    text = _emoji.sub('', _url.sub('', msg_content))
    en, jp, total = get_character_spread(text)
    return en / total if total else None


def get_character_spread(text):
    english = 0
    japanese = 0
    for ch in text:
        if is_cjk(ch):
            japanese += 1
        elif is_english(ch):
            english += 1
    return english, japanese, english + japanese


def is_ignored_emoji(char):
    # noinspection PyPep8Naming
    EMOJI_MAPPING = (
        (0x0080, 0x02AF),
        (0x0300, 0x03FF),
        (0x0600, 0x06FF),
        (0x0C00, 0x0C7F),
        (0x1DC0, 0x1DFF),
        (0x1E00, 0x1EFF),
        (0x2000, 0x209F),
        (0x20D0, 0x214F)
    )
    return any(start <= ord(char) <= end for start, end in EMOJI_MAPPING)


def is_cjk(char):
    # noinspection PyPep8Naming
    CJK_MAPPING = (
        (0x3040, 0x30FF),  # Hiragana + Katakana
        (0xFF66, 0xFF9D),  # Half-Width Katakana
        (0x4E00, 0x9FAF)  # Common/Uncommon Kanji
    )
    return any(start <= ord(char) <= end for start, end in CJK_MAPPING)


def is_english(char):
    # basically English characters save for w because of laughter
    # noinspection PyPep8Naming
    RANGE_CHECK = (
        (0x61, 0x76),  # a to v
        (0x78, 0x7a),  # x to z
        (0x41, 0x56),  # A to V
        (0x58, 0x5a),  # X to Z
        (0xFF41, 0xFF56),  # ａ to ｖ
        (0xFF58, 0xFF5A),  # ｘ to ｚ
        (0xFF21, 0xFF36),  # Ａ to Ｖ
        (0xFF58, 0xFF3A),  # Ｘ to Ｚ
    )
    return any(start <= ord(char) <= end for start, end in RANGE_CHECK)


async def send_error_embed(bot: discord.Client,
                           ctx_or_event: Union[commands.Context, discord.Interaction, str],
                           error: BaseException,
                           *args, **kwargs):
    """This can be called from:
    - main.on_command_error
    - main.on_error
    - main.on_tree_error
    - RaiView.on_error"""
    try:
        await send_error_embed_internal(bot, ctx_or_event, error, *args, **kwargs)
    except Exception as e:
        exc = ''.join(traceback.format_exception(type(e), e, e.__traceback__, chain=False))
        logging.error(f"Error in send_error_embed: {exc}")


async def send_error_embed_internal(bot: discord.Client,
                                    ctx_or_event: Union[commands.Context, discord.Interaction, str],
                                    error: BaseException,
                                    *args, **kwargs):

    # Determine if it's a command/interaction or an event
    # this is a command error / application error
    print(f"send error embed internal, {type(args)}, {args}")
    if isinstance(ctx_or_event, (commands.Context, discord.Interaction)):
        ctx = ctx_or_event
        msg = ctx.message if isinstance(ctx, commands.Context) else None

        try:
            qualified_name = getattr(ctx.command, 'qualified_name', ctx.command.name)
        except AttributeError:
            qualified_name = "Non-command"

        e = discord.Embed(title=f'Command Error ({qualified_name})', colour=0xcc3366)

        fmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'
        if ctx.guild:
            fmt = f'{fmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})'
        e.add_field(name='Location', value=fmt, inline=False)

    # this is an event error
    else:
        event = ctx_or_event
        msg = None

        qualified_name = event
        e = discord.Embed(title='Event Error', colour=0xa32952)
        e.add_field(name='Event', value=event)
        e.timestamp = discord.utils.utcnow()

    # Extract useful information from args (like guild, author, channel)
    extra_info = {}
    jump_url = ""

    args_str = ['```py']
    for index, arg in enumerate(args):
        if not arg:
            continue

        args_str.append(f'[{index}]: {arg!r}')
        if isinstance(arg, discord.Message):
            msg = arg
            extra_info['content'] = arg.content
            extra_info['author_id'] = arg.author.id
            extra_info['channel_id'] = arg.channel.id
            if arg.guild:
                extra_info['guild_id'] = arg.guild.id

        else:
            if hasattr(arg, 'guild_id'):
                extra_info['guild_id'] = arg.guild_id
            if hasattr(arg, 'channel_id'):
                extra_info['channel_id'] = arg.channel_id
            if hasattr(arg, 'author_id'):
                extra_info['author_id'] = arg.author_id

    args_str.append('```')
    if args:
        e.add_field(name='Args', value='\n'.join(args_str), inline=False)

    # Attach author info if available
    if msg:
        jump_url = msg.jump_url
        e.add_field(name="Author", value=f'{msg.author} ({msg.author.mention}, ID: {msg.author.id})')
        e.add_field(name="Message Content", value=f'{jump_url}\n```{msg.content[:1024 - 6 - 86 - 1]}```', inline=False)


    # Include guild/channel details if available
    if 'guild_id' in extra_info:
        guild = bot.get_guild(extra_info['guild_id'])
        if guild:
            e.add_field(name='Guild', value=f'{guild} (ID: {guild.id})', inline=False)
    if 'channel_id' in extra_info:
        channel = bot.get_channel(extra_info['channel_id'])
        e.add_field(name='Channel', value=f'{channel.mention}', inline=False)

    # Log the error to the console and logging system
    print(datetime.now(), file=sys.stderr)
    print(f'Error in {qualified_name}:', file=sys.stderr)
    print(f'{error.__class__.__name__}: {error}', file=sys.stderr)

    exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=True))
    logging.error(f"Error in {qualified_name}: {exc}")

    # Split the traceback into multiple messages if it's too long
    traceback_segments = split_text_into_segments(exc, 1900)

    # Get the logging channel
    traceback_logging_channel_id = os.getenv("ERROR_CHANNEL_ID") or os.getenv("TRACEBACK_LOGGING_CHANNEL")
    if not traceback_logging_channel_id:
        logging.error("No error channel ID found in environment variables.")
        return

    traceback_channel = bot.get_channel(int(traceback_logging_channel_id))
    if not traceback_channel:
        logging.error(f"Could not find error logging channel with ID {traceback_logging_channel_id}.")
        return

    # Send the traceback in segments to avoid hitting the Discord limit
    try:
        for index, segment in enumerate(traceback_segments):
            if index != len(traceback_segments) - 1:
                await traceback_channel.send(f"```py\n{segment}```")
            else:
                await traceback_channel.send(f"```py\n{segment}```", embed=e)
    except discord.Forbidden:
        logging.error("Bot lacks permission to send messages in the traceback channel.")
    except discord.HTTPException as http_error:
        logging.error(f"Failed to send error message: {http_error}")

    print('')  # Empty print for spacing in logs


# async def send_error_embed(bot: discord.Client,
#                            ctx: Union[commands.Context, discord.Interaction],
#                            error: Exception,
#                            embed: discord.Embed):
#     error = getattr(error, 'original', error)
#     try:
#         qualified_name = getattr(ctx.command, 'qualified_name', ctx.command.name)
#     except AttributeError:  # ctx.command.name is also None
#         qualified_name = "Non-command"
#     traceback.print_tb(error.__traceback__)
#     print(discord.utils.utcnow())
#     print(f'Error in {qualified_name}:', file=sys.stderr)
#     print(f'{error.__class__.__name__}: {error}', file=sys.stderr)
#
#     exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
#     if ctx.message:
#         traceback_text = f'{ctx.message.jump_url}\n```py\n{exc}```'
#     elif ctx.channel:
#         traceback_text = f'{ctx.channel.mention}\n```py\n{exc}```'
#     else:
#         traceback_text = f'```py\n{exc}```'
#
#     embed.timestamp = discord.utils.utcnow()
#     traceback_logging_channel = int(os.getenv("TRACEBACK_LOGGING_CHANNEL"))
#     view = None
#     if ctx.message:
#         view = discord.ui.View.from_message(ctx.message)
#     await bot.get_channel(traceback_logging_channel).send(traceback_text[-2000:], embed=embed, view=view)
#     print('')


class RaiView(discord.ui.View):
    async def on_error(self,
                       interaction: discord.Interaction,
                       error: Exception,
                       item: Union[discord.ui.Button, discord.ui.Select, discord.ui.TextInput]):
        e = discord.Embed(title=f'View Component Error ({str(item.type)})', colour=0xcc3366)
        e.add_field(name='Interaction User', value=f"{interaction.user} ({interaction.user.mention})")

        fmt = f'Channel: {interaction.channel} (ID: {interaction.channel.id})'
        if interaction.guild:
            fmt = f'{fmt}\nGuild: {interaction.guild} (ID: {interaction.guild.id})'

        e.add_field(name='Location', value=fmt, inline=False)

        if hasattr(item, "label"):
            e.add_field(name="Item label", value=item.label)

        if interaction.data:
            e.add_field(name="Data", value=f"```{interaction.data}```", inline=False)

        if interaction.extras:
            e.add_field(name="Extras", value=f"```{interaction.extras}```")

        await send_error_embed(interaction.client, interaction, error, e)


async def aiohttp_get(url: str, headers: dict = None) -> bytes:
    """Wrapper just for getting the response"""
    if isinstance(url, commands.Context):
        raise ValueError("You passed a context to aiohttp_get instead of a URL")
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            return await resp.read()
        
        
async def _aiohttp_get_text(url: str, headers: dict = None) -> (aiohttp.ClientResponse, str):
    """Wrapper just for getting the response"""
    if isinstance(url, commands.Context):
        raise ValueError("You passed a context to _aiohttp_get_text instead of a URL")
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            return resp, (await resp.text())


async def aiohttp_get_text(ctx: commands.Context = None, url: str = "", headers: dict = None) -> str:
    if not url:
        raise ValueError("No URL provided to aiohttp_get")
    
    text: str
    
    try:
        response, text = await _aiohttp_get_text(url, headers=headers)
    except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
        if ctx:
            await safe_send(ctx, f'invalid_url:  Your URL was invalid ({url})')
        else:
            raise ValueError(f'invalid_url:  Your URL was invalid ({url})')
        return ''

    if not text:
        if ctx:
            await safe_send(ctx, embed=red_embed("I received nothing from the site for your search query."))
        else:
            raise ValueError("I received nothing from the site for your search query.")
        return ''

    if response.status == 200:
        return text
    else:
        if ctx:
            await safe_send(ctx, f'html_error: Error {response.status}: {response.reason} ({url})')
        else:
            raise ValueError(f'html_error: Error {response.status}: {response.reason} ({url})')
        return ''


def asyncio_task(func: Callable, *args, **kwargs):
    if not isinstance(func, Callable):
        raise ValueError("The first argument must be a callable function.")
    
    if "task_name" in kwargs:
        task_name = kwargs["task_name"]
        del kwargs["task_name"]
    else:
        task_name = func.__qualname__
    
    if asyncio.iscoroutinefunction(func):
        coro = func(*args, **kwargs)  # Create coroutine
    else:
        # If not a coroutine function, wrap it in an async function
        async def wrapper():
            return func(*args, **kwargs)
        
        coro = wrapper()
        
    task = asyncio.create_task(coro, name=task_name)
    task.set_name(task_name)
    task.add_done_callback(asyncio_task_done_callback)
    return task

def asyncio_task_done_callback(task: asyncio.Task):
    try:
        coro_name = task.get_coro().__qualname__
        if task.exception():
            print(f"Error in {coro_name}: {task.exception()}")
            asyncio_task(send_error_embed, here.bot, coro_name, task.exception())
        else:
            pass
            # print(f"Task {coro_name} completed successfully.")
    except asyncio.CancelledError:
        print(f"Task {task.get_coro().__qualname__} was cancelled.")
    except Exception as e:
        print(f"Unexpected error in task callback: {e}")


def split_text_into_segments(text, segment_length=1024) -> list[str]:
    """Split a long text into segments of a specified length."""
    segments = []
    while len(text) > segment_length:
        # Find the last new line before the segment limit to avoid breaking words
        split_index = text.rfind('\n', 0, segment_length)
        if split_index == -1:  # If no new line is found, split at space
            split_index = text.rfind(' ', 0, segment_length)
            if split_index == -1:  # If no space is found, split at the limit
                split_index = segment_length
        segments.append(text[:split_index])
        text = text[split_index:].lstrip()  # Remove leading spaces in the next segment
    segments.append(text)  # Append the last segment
    return segments
    

class RaiModal(discord.ui.Modal):
    async def on_error(self,
                       interaction: discord.Interaction,
                       error: Exception):
        e = discord.Embed(title=f'Modal Component Error', colour=0xcc3366)
        e.add_field(name='Interaction User', value=f"{interaction.user} ({interaction.user.mention})")

        fmt = f'Channel: {interaction.channel} (ID: {interaction.channel.id})'
        if interaction.guild:
            fmt = f'{fmt}\nGuild: {interaction.guild} (ID: {interaction.guild.id})'

        e.add_field(name='Location', value=fmt, inline=False)

        if interaction.data:
            e.add_field(name="Data", value=f"```{interaction.data}```", inline=False)

        if interaction.extras:
            e.add_field(name="Extras", value=f"```{interaction.extras}```")

        await send_error_embed(interaction.client, interaction, error, e)
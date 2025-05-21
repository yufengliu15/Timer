import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TOKEN')
COMMAND_PREFIX = '!' 

intents = discord.Intents.default()
intents.message_content = True  # Required for commands to be processed
intents.members = True          # Recommended for user mentions and member properties
                                # Enable "Server Members Intent" in your bot's Developer Portal settings.

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=commands.DefaultHelpCommand())

timer_running = False
timer_seconds_remaining = 0
timer_participants = set()    
timer_message_channel = None  
timer_starter = None          

# --- Helper function to format time (remains the same) ---
def format_time(seconds):
    """Converts seconds to a string in MM:SS or HH:MM:SS format if hours are present."""
    if seconds < 0: seconds = 0
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

# --- Timer Task (core logic remains similar, interacts with global state) ---
@tasks.loop(seconds=1)
async def timer_tick():
    global timer_seconds_remaining, timer_running, timer_participants, timer_message_channel, timer_starter

    if not timer_running: # If flag is false (e.g., due to !stop), stop the task loop
        timer_tick.stop()
        return

    timer_seconds_remaining -= 1

    if timer_seconds_remaining <= 0:
        # Timer has ended
        current_channel = timer_message_channel
        current_participants = list(timer_participants) # Create a copy

        # Critical: Set running to false and stop the task loop *before* sending messages
        timer_running = False
        timer_tick.stop() 

        if current_channel:
            mentions = " ".join([user.mention for user in current_participants])
            if current_participants:
                await current_channel.send(f"⏰ Timer ended! {mentions} Time's up!")
            else:
                await current_channel.send("⏰ Timer ended! No one had joined.")
        
        # Reset global state associated with the timer
        timer_participants.clear()
        timer_message_channel = None
        timer_starter = None

@timer_tick.before_loop
async def before_timer_tick_task():
    """Ensures the bot is ready before the task loop starts."""
    await bot.wait_until_ready()
    print("Timer task loop is about to start.")

@timer_tick.after_loop
async def after_timer_tick_task():
    """Handles cleanup or error notification if the task loop stops unexpectedly."""
    global timer_running, timer_seconds_remaining, timer_participants, timer_message_channel, timer_starter
    
    print(f"Timer_tick loop has finished. Was cancelled by task.cancel(): {timer_tick.is_being_cancelled()}. Current 'timer_running' flag: {timer_running}")

    if timer_running: 
        print("CRITICAL: Timer task stopped unexpectedly while 'timer_running' was True. Resetting timer state.")
        if timer_message_channel:
            try:
                await timer_message_channel.send("⚠️ The timer encountered an unexpected issue and has been stopped.")
            except discord.errors.Forbidden:
                print(f"Missing permissions to send message in channel {timer_message_channel.name} ({timer_message_channel.id}) during after_loop cleanup.")
            except Exception as e:
                print(f"Error sending unexpected stop message in after_loop: {e}")
        
        timer_running = False
        timer_seconds_remaining = 0
        timer_participants.clear()
        timer_message_channel = None
        timer_starter = None
    print("Timer state after loop completion is expected to be clean or handled.")

# --- Bot Events ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print(f"Bot is ready and listening for commands with prefix '{COMMAND_PREFIX}'")
    print(f"Use {COMMAND_PREFIX}help for a list of commands.")
    print(f"Invite link: https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot") # Adjust permissions as needed

# --- Timer Commands ---
@bot.command(name='start', help='Starts a timer for a specified number of minutes. Usage: !start <minutes>')
async def start_timer_command(ctx, minutes: int): # Type hint 'int' for automatic conversion
    global timer_running, timer_seconds_remaining, timer_participants, timer_message_channel, timer_starter

    if timer_running:
        await ctx.send(f"A timer is already in progress with **{format_time(timer_seconds_remaining)}** left (started in #{timer_message_channel.name if timer_message_channel else 'an unknown channel'}).\nUse `!stop` to end it first.")
        return

    if minutes <= 0:
        await ctx.send("Please provide a positive number of minutes (e.g., `!start 1`).")
        return
    
    if minutes > 120: 
         await ctx.send("The maximum timer duration is 120 minutes (2 hours). Please choose a shorter duration.")
         return

    # Initialize timer state
    timer_seconds_remaining = minutes * 60
    timer_participants.clear()
    timer_participants.add(ctx.author) # Starter joins automatically
    timer_message_channel = ctx.channel
    timer_starter = ctx.author
    timer_running = True # Set running flag *before* starting the task

    try:
        # If timer_running was false, timer_tick should not be running.
        # If it is (inconsistent state), timer_tick.start() will raise RuntimeError.
        if timer_tick.is_running(): # Should ideally not happen if timer_running was False
            print("Warning: timer_tick found running before start. Attempting to restart.")
            timer_tick.restart() # Safely restarts: cancels, calls before_loop, then starts.
        else:
            timer_tick.start()
        await ctx.send(f"⏳ Timer started by {ctx.author.mention} for **{minutes} minute(s)** ({format_time(timer_seconds_remaining)}).\nYou've been automatically joined!\nOthers can join with `!join`.\nUse `!timeremaining` to check time or `!stop` to end early.")
    except RuntimeError as e:
        if "Loop is already running" in str(e):
            await ctx.send(f"Error: The timer task seems to be already running. This might indicate an inconsistent state. Please try `!stop` and then `!start` again.")
        else:
            await ctx.send(f"An unexpected runtime error occurred while starting the timer: {e}")
        # Reset state as a precaution if starting failed critically
        timer_running = False 
        timer_message_channel = None
        timer_starter = None
        timer_participants.clear()
    except Exception as e:
        print(f"General error in !start command: {e}")
        await ctx.send("An unexpected error occurred while trying to start the timer.")
        timer_running = False
        if timer_tick.is_running(): timer_tick.cancel() # Attempt to stop if it somehow started
        timer_participants.clear()
        timer_message_channel = None
        timer_starter = None

@bot.command(name='join', help='Joins the current timer session if active in this channel.')
async def join_timer_command(ctx):
    global timer_running, timer_participants, timer_message_channel

    if not timer_running:
        await ctx.send(f"No timer is currently running. Start one with `{COMMAND_PREFIX}start <minutes>`.")
        return
    
    if timer_message_channel != ctx.channel:
        await ctx.send(f"A timer is running in **#{timer_message_channel.name}**. Please use `{COMMAND_PREFIX}join` in that channel.")
        return

    if ctx.author in timer_participants:
        await ctx.send(f"{ctx.author.mention}, you've already joined the timer!")
    else:
        timer_participants.add(ctx.author)
        await ctx.send(f"{ctx.author.mention} has joined the timer! ({len(timer_participants)} total participant(s)).")

@bot.command(name='timeremaining', aliases=['timeleft', 'tr'], help='Shows the time remaining on the current timer.')
async def timeremaining_command(ctx):
    global timer_running, timer_seconds_remaining, timer_message_channel

    if not timer_running:
        await ctx.send("No timer is currently running.")
        return
    
    if timer_message_channel != ctx.channel:
         await ctx.send(f"A timer is currently active in **#{timer_message_channel.name}** with **{format_time(timer_seconds_remaining)}** remaining.")
    else:
        await ctx.send(f"⏳ Time remaining: **{format_time(timer_seconds_remaining)}**")

@bot.command(name='stop', help='Stops the current active timer.')
async def stop_timer_command(ctx):
    global timer_running, timer_seconds_remaining, timer_participants, timer_message_channel, timer_starter

    if not timer_running:
        await ctx.send("No timer is currently running to stop.")
        return

    # Optional: Restriction to starter or admin (example)
    # if ctx.author != timer_starter and not ctx.author.guild_permissions.manage_guild:
    #     await ctx.send(f"Only {timer_starter.mention} (who started the timer) or an admin can stop it.")
    #     return

    original_channel_for_stop_message = timer_message_channel
    original_participants_for_stop_message = list(timer_participants)

    timer_running = False # Set flag first
    if timer_tick.is_running():
        timer_tick.cancel() 

    # Clear global state associated with the timer
    timer_seconds_remaining = 0
    timer_participants.clear()
    timer_message_channel = None
    timer_starter = None

    if original_channel_for_stop_message:
        mentions = " ".join([user.mention for user in original_participants_for_stop_message])
        await original_channel_for_stop_message.send(f"⏱️ Timer stopped by {ctx.author.mention}. {mentions if mentions else 'No one had joined.'}")
    else: 
        await ctx.channel.send(f"⏱️ Timer stopped by {ctx.author.mention}. (Timer channel context was lost).")
        print("Warning: timer_message_channel was None during !stop despite timer_running being true.")

# --- Error Handling for commands ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Oops! You missed an argument: `{error.param.name}`. Use `{COMMAND_PREFIX}help {ctx.command.name}` for usage details.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Hmm, that's not quite right. The argument you provided for `{error.param.name if hasattr(error, 'param') else 'one of the inputs'}` seems to be the wrong type. Use `{COMMAND_PREFIX}help {ctx.command.name}` for usage details.")
    elif isinstance(error, commands.CommandNotFound):
        # You can choose to ignore this or send a message
        # await ctx.send(f"Sorry, I don't recognize the command `{ctx.invoked_with}`. Try `{COMMAND_PREFIX}help`.")
        print(f"Command not found: {ctx.invoked_with}") # Silently log or ignore
    elif isinstance(error, commands.CommandInvokeError):
        print(f"An error occurred in command '{ctx.command.name}': {error.original}")
        await ctx.send(f"An internal error occurred while running `{ctx.command.name}`. The developers have been alerted (check the console!).")
    else:
        print(f"An unexpected error occurred: {error}")
        await ctx.send("An unexpected error occurred. Please try again.")

if __name__ == "__main__":
    if TOKEN:
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("CRITICAL: LoginFailure - Check your bot TOKEN. It might be invalid or expired.")
        except discord.errors.PrivilegedIntentsRequired:
            print("CRITICAL: PrivilegedIntentsRequired - Ensure 'Server Members Intent' and 'Message Content Intent' are enabled in your bot's settings on the Discord Developer Portal.")
        except Exception as e:
            print(f"CRITICAL: An error occurred while trying to run the bot: {e}")
    else:
        print("CRITICAL: Discord bot TOKEN not found. Please set it in your .env file or as an environment variable.")
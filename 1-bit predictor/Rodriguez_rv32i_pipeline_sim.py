#!/usr/bin/env python3
"""
CS4200 - Assignment 5 (TEMPLATE)
RV32I 5-stage pipelined simulator (IF/ID/EX/MEM/WB)
You must complete all TODO sections.

Pipeline model requirements:
- Pipeline registers: IF/ID, ID/EX, EX/MEM, MEM/WB
- Forwarding into EX stage from:
    - EX/MEM (when value is ready, i.e., NOT a load)
    - MEM/WB (ALU or load result)
- Load-use stall:
    if ID uses a register that EX (ID/EX) will load, stall 1 cycle:
      - freeze PC and IF/ID
      - insert bubble into ID/EX
- Control hazard flush:
    resolve branch/jump in EX; if taken:
      - redirect PC
      - flush IF/ID (wrong-path instruction)
      - ensure next ID/EX is bubble

Supported subset:
R-type: add, sub, and, or, xor, sll, srl, sra, slt, sltu
I-type: addi, andi, ori, xori, slti, sltiu, slli, srli, srai
Mem: lw, sw
Branch: beq, bne, blt, bge, bltu, bgeu
Jump: jal, jalr
"""

MASK32 = 0xFFFFFFFF


# ------------------------------------------------------------
# 32-bit helpers
# ------------------------------------------------------------

def u32(x):
    """TODO: return x as 32-bit unsigned (mask with 0xFFFFFFFF)."""
    return x & 0xFFFFFFFF


def s32(x):
    """TODO: interpret x as signed 32-bit two's complement (return Python int)."""
    temp = x & 0xFFFFFFFF
    if temp & 0x80000000 == 0x80000000:
        return temp - 2**32
    return temp

def sign_extend(value, bits):
    """
    TODO: sign-extend 'value' which is 'bits' wide.
    Example: sign_extend(0b1111, 4) -> -1
    """
    sign_bit = 1 << (bits-1)
    return (value & (sign_bit-1)) - (value & sign_bit)


def get_bits(x, hi, lo):
    """TODO: extract bits [hi:lo] inclusive."""
    mask = (1 << (hi-lo+1)) - 1
    return (x >> lo) & mask


# ------------------------------------------------------------
# Immediate generators
# ------------------------------------------------------------

def imm_i(instr):
    """TODO: I-type immediate: bits[31:20] sign-extended."""
    return sign_extend(get_bits(instr, 31, 20), 12)


def imm_s(instr):
    """TODO: S-type immediate: bits[31:25] + bits[11:7] sign-extended."""
    return sign_extend((get_bits(instr, 31, 25) << 5) + get_bits(instr, 11, 7), 12)


def imm_b(instr):
    """
    TODO: B-type immediate (branch):
      imm[12]=instr[31], imm[11]=instr[7], imm[10:5]=instr[30:25], imm[4:1]=instr[11:8], imm[0]=0
    sign-extend 13 bits
    """
    return sign_extend((get_bits(instr, 31, 31) << 12) + (get_bits(instr, 7, 7) << 11) + (get_bits(instr, 30, 25) << 5) + (get_bits(instr, 11, 8) << 1), 13)


def imm_u(instr):
    """TODO: U-type immediate: bits[31:12] << 12."""
    return get_bits(instr, 31, 12) << 12


def imm_j(instr):
    """
    TODO: J-type immediate (jal):
      imm[20]=instr[31], imm[10:1]=instr[30:21], imm[11]=instr[20], imm[19:12]=instr[19:12], imm[0]=0
    sign-extend 21 bits
    """
    return sign_extend((get_bits(instr, 31, 31) << 20) + (get_bits(instr, 19, 12) << 12) + (get_bits(instr, 20, 20) << 11) + (get_bits(instr, 30, 21) << 1), 21)


# ------------------------------------------------------------
# Decode + Control
# ------------------------------------------------------------

def decode(instr):
    """
    TODO: return dict with fields:
      instr, opcode, rd, funct3, rs1, rs2, funct7
      imm_I, imm_S, imm_B, imm_U, imm_J
    """
    d = {}
    d["instr"] = instr
    d["opcode"] = get_bits(instr, 6, 0)
    d["rd"] = get_bits(instr, 11, 7)
    d["funct3"] = get_bits(instr, 14, 12)
    d["rs1"] = get_bits(instr, 19, 15)
    d["rs2"] = get_bits(instr, 24, 20)
    d["funct7"] = get_bits(instr, 31, 25)

    d["imm_I"] = imm_i(instr)
    d["imm_S"] = imm_s(instr)
    d["imm_B"] = imm_b(instr)
    d["imm_U"] = imm_u(instr)
    d["imm_J"] = imm_j(instr)
    return d


def main_control(d):
    """
    TODO: Implement control signals as dict.
    Required keys:
      RegWrite, MemRead, MemWrite, MemToReg, ALUSrc, Branch, Jump, JumpReg,
      ALUOp ("R","I","ADDR","BR"), ImmSel ("I","S","B","U","J" or None),
      BrType ("beq","bne","blt","bge","bltu","bgeu" or None),
      IsNOP (1 if treated as NOP)
    Treat instr==0 as NOP.
    """
    c = {
        "RegWrite": 0,
        "MemRead": 0,
        "MemWrite": 0,
        "MemToReg": 0,
        "ALUSrc": 0,
        "Branch": 0,
        "Jump": 0,
        "JumpReg": 0,
        "ALUOp": None,
        "ImmSel": None,
        "BrType": None,
        "IsNOP": 0,
    }
    opcode = d["opcode"]
    funct3 = d["funct3"]
    
    if opcode == 0x33: # R-Type
        c["RegWrite"] = 1
    elif opcode == 0x13: # I-Type
        c["RegWrite"] = 1
        c["ALUSrc"] = 1
        c["ImmSel"] = "I"
    elif opcode == 0x03: # lw
        c["RegWrite"] = 1
        c["MemRead"] = 1
        c["MemToReg"] = 1
        c["ALUSrc"] = 1
        c["ImmSel"] = "I"
        c["ALUOp"] = "ADD"
    elif opcode == 0x23: # sw
        c["MemWrite"] = 1
        c["ALUSrc"] = 1
        c["ImmSel"] = "S"
        c["ALUOp"] = "ADD"
    elif opcode == 0x63: # branches
        c["Branch"] = 1
        c["ImmSel"] = "B"
        c["ALUOp"] = "SUB"
        if funct3 == 0b000:
            c["BrType"] = "beq"
        elif funct3 == 0b001:
            c["BrType"] = "bne"
        elif funct3 == 0b100:
            c["BrType"] = "blt"
        elif funct3 == 0b101:
            c["BrType"] = "bge"
        elif funct3 == 0b110:
            c["BrType"] = "bltu"
        elif funct3 == 0b111:
            c["BrType"] = "bgeu"
    elif opcode == 0x6F: # jal
        c["RegWrite"] = 1
        c["ALUSrc"] = 1
        c["Jump"] = 1
        c["ImmSel"] = "J"
        c["ALUOp"] = "ADD"
    elif opcode == 0x67: # jalr
        c["RegWrite"] = 1
        c["ALUSrc"] = 1
        c["Jump"] = 1
        c["JumpReg"] = d["rs1"]
        c["ImmSel"] = "I"
        c["ALUOp"] = "ADD"
    
    if c["ALUOp"] == None: # This is handled for individual instructions whenever it's easier to do it within this function.
        c["ALUOp"] = alu_control(c, d)

    if d["instr"] == 0:
        c["IsNOP"] = 1

    return c


def select_imm(d, c):
    """TODO: select immediate based on c['ImmSel'] else return 0."""
    ImmSel = c["ImmSel"]

    if ImmSel == "I":
        return d["imm_I"]
    if ImmSel == "S":
        return d["imm_S"]
    if ImmSel == "J":
        return d["imm_J"]
    if ImmSel == "B":
        return d["imm_B"]
    if ImmSel == "U":
        return d["imm_U"]
    return 0


# ------------------------------------------------------------
# ALU control + ALU
# ------------------------------------------------------------

def alu_control(c, d):
    """
    TODO: return ALU op string based on:
      - c['ALUOp']
      - funct3/funct7
    Output must be one of:
      ADD SUB AND OR XOR SLL SRL SRA SLT SLTU
    """
    funct3 = d["funct3"]
    funct7 = d["funct7"]

    if d["opcode"] == 0x33: # R-Type
        if funct3 == 0b000 and funct7 == 0b0000000:
            return "ADD"
        elif funct3 == 0b000 and funct7 == 0b0100000:
            return "SUB"
        elif funct3 == 0b111 and funct7 == 0b0000000:
            return "AND"
        elif funct3 == 0b110 and funct7 == 0b0000000:
            return "OR"
        elif funct3 == 0b100 and funct7 == 0b0000000:
            return "XOR"
        elif funct3 == 0b001 and funct7 == 0b0000000:
            return "SLL"
        elif funct3 == 0b101 and funct7 == 0b0000000:
            return "SRL"
        elif funct3 == 0b101 and funct7 == 0b0100000:
            return "SRA"
        elif funct3 == 0b010 and funct7 == 0b0000000:
            return "SLT"
        elif funct3 == 0b011 and funct7 == 0b0000000:
            return "SLTU"
    
    else: # I-Type
        if funct3 == 0b000:
            return "ADD"
        elif funct3 == 0b111:
            return "AND"
        elif funct3 == 0b110:
            return "OR"
        elif funct3 == 0b100:
            return "XOR"
        elif funct3 == 0b001:
            return "SLL"
        elif funct3 == 0b101 and funct7 == 0b0000000:
            return "SRL"
        elif funct3 == 0b101 and funct7 == 0b0100000:
            return "SRA"
        elif funct3 == 0b010:
            return "SLT"
        elif funct3 == 0b011:
            return "SLTU"


def alu_exec(alu_op, a, b):
    """
    TODO: execute ALU op with 32-bit wraparound.
    Shift amount = b & 0x1F
    SLT uses signed compare, SLTU uses unsigned compare.
    SRA must be arithmetic shift (signed).
    """
    if alu_op == "ADD":
        return u32(a + b)
    if alu_op == "SUB":
        return u32(a - b)
    if alu_op == "AND":
        return a & b
    if alu_op == "OR":
        return a | b
    if alu_op == "XOR":
        return a ^ b
    if alu_op == "SLL":
        return u32(a << (b & 0x1F))
    if alu_op == "SRL":
        return u32(a >> (b & 0x1F))
    if alu_op == "SRA":
        return u32(s32(a) >> (b & 0x1F))
    if alu_op == "SLT":
        if s32(a) < s32(b):
            return 1
        else:
            return 0
    if alu_op =="SLTU":
        if u32(a) < u32(b):
            return 1
        return 0


def branch_taken(br_type, rs1_val, rs2_val):
    """
    TODO: implement branch comparisons:
      beq:  rs1 == rs2
      bne:  rs1 != rs2
      blt:  signed(rs1) <  signed(rs2)
      bge:  signed(rs1) >= signed(rs2)
      bltu: unsigned(rs1) <  unsigned(rs2)
      bgeu: unsigned(rs1) >= unsigned(rs2)
    """
    if br_type == "beq" and rs1_val == rs2_val:
        return True
    if br_type == "bne" and rs1_val != rs2_val:
        return True
    if br_type == "blt" and s32(rs1_val) < s32(rs2_val):
        return True
    if br_type == "bge" and s32(rs1_val) >= s32(rs2_val):
        return True
    if br_type == "bltu" and rs1_val < rs2_val:
        return True
    if br_type == "bgeu" and rs1_val >= rs2_val:
        return True
    return False


# ------------------------------------------------------------
# Data memory (word aligned)
# ------------------------------------------------------------

def dmem_load_word(dmem, addr):
    """
    TODO:
      - enforce 4-byte alignment (addr % 4 == 0)
      - return dmem.get(addr, 0) masked to 32-bit
    """
    if addr % 4 == 0:
        return u32(dmem.get(addr, 0))
    return None


def dmem_store_word(dmem, addr, value):
    """
    TODO:
      - enforce 4-byte alignment
      - store 32-bit value into dmem[addr]
    """
    if addr % 4 == 0:
        dmem[addr] = value


# ------------------------------------------------------------
# Pipeline registers
# ------------------------------------------------------------

def make_if_id():
    """IF/ID pipeline register bundle."""
    return {"valid": 0, "pc": 0, "instr": 0}


def make_id_ex():
    """ID/EX pipeline register bundle."""
    return {
        "valid": 0,
        "pc": 0,
        "pc_plus4": 0,
        "d": None,
        "c": None,
        "imm": 0,
        "rs1": 0,
        "rs2": 0,
        "rd": 0,
        "rs1_val": 0,
        "rs2_val": 0,
        "alu_op": "ADD",
    }


def make_ex_mem():
    """EX/MEM pipeline register bundle."""
    return {
        "valid": 0,
        "pc_plus4": 0,
        "c": None,
        "d": None,
        "rd": 0,
        "alu_res": 0,
        "rs2_val_fwd": 0,     # store data after forwarding
        "mem_addr": 0,
        "branch_taken": 0,
        "next_pc": 0,
        "wb_val_for_jumps": 0 # pc+4 for jal/jalr
    }


def make_mem_wb():
    """MEM/WB pipeline register bundle."""
    return {
        "valid": 0,
        "pc_plus4": 0,
        "c": None,
        "d": None,
        "rd": 0,
        "alu_res": 0,
        "mem_data": 0,
        "wb_val_for_jumps": 0
    }


# ------------------------------------------------------------
# Hazard detection helpers
# ------------------------------------------------------------

def uses_rs1(d):
    """
    TODO: return True if instruction uses rs1.
    Hint: most ops use rs1 except jal (and NOP).
    """
    return not (d["instr"] == 0 or d["opcode"] == 0x6F)


def uses_rs2(d):
    """
    TODO: return True if instruction uses rs2.
    Hint: R-type, sw, and branches use rs2.
    """
    return (d["opcode"] == 0x63 or d["opcode"] == 0x23 or d["opcode"] == 0x33)


def is_load_c(c):
    """
    TODO: return True if control signals represent a load:
      MemRead==1 and MemToReg==1
    """
    return (c["MemRead"] == 1 and c["MemToReg"] == 1)


def will_write_c(c):
    """TODO: return True if RegWrite==1."""
    return c["RegWrite"] == 1


def forwarding_select(src_reg, ex_mem, mem_wb):
    """
    TODO: implement forwarding decision for a source register used in EX stage.

    Return (use_forward, value)

    Priority:
      1) EX/MEM if it will write rd and rd matches src_reg AND it is NOT a load.
         Value to forward:
           - if instruction is jal/jalr: forward wb_val_for_jumps (pc+4)
           - else forward alu_res
      2) MEM/WB if it will write rd and rd matches src_reg.
         Value to forward:
           - if jal/jalr: wb_val_for_jumps
           - if load (MemToReg): mem_data
           - else: alu_res

    Note:
      - Never forward to src_reg==0 (x0)
      - EX/MEM forwarding cannot provide load data (not available until MEM/WB)
    """
    if src_reg == 0:
        return False, 0
    elif ex_mem["valid"] == 1 and ex_mem["c"]["RegWrite"] == 1 and ex_mem["rd"] == src_reg and ex_mem["d"]["opcode"] != 0x03:
        if ex_mem["c"]["Jump"] == 1:
            return True, ex_mem["wb_val_for_jumps"]
        else:
            return True, ex_mem["alu_res"]
    elif mem_wb["valid"] == 1 and mem_wb["c"]["RegWrite"] == 1 and mem_wb["rd"] == src_reg:
        if mem_wb["c"]["Jump"] == 1:
            return True, mem_wb["wb_val_for_jumps"]
        elif mem_wb["d"]["opcode"] == 0x03:
            return True, mem_wb["mem_data"]
        else:
            return True, mem_wb["alu_res"]
    return False, 0


def load_use_hazard(if_id, id_ex):
    """
    TODO: detect classic load-use hazard.

    If ID/EX is a load writing rd,
    and IF/ID instruction uses that rd as rs1 or rs2,
    then return True (need stall).

    Stall action (in main loop):
      - freeze PC and IF/ID (no new fetch)
      - insert bubble into ID/EX for 1 cycle
    """
    if id_ex["valid"] == 1 and id_ex["d"] is not None and id_ex["c"] is not None:
        if id_ex["c"]["MemRead"] == 1 and id_ex["c"]["MemToReg"] == 1:
            return (id_ex["d"]["opcode"] == 0x03 and ((uses_rs1(decode(if_id["instr"])) and decode(if_id["instr"])["rs1"] == id_ex["d"]["rd"]) or (uses_rs2(decode(if_id["instr"])) and decode(if_id["instr"])["rs2"] == id_ex["d"]["rd"])))
    return False

# ------------------------------------------------------------
# Trace helpers
# ------------------------------------------------------------

def try_mnemonic(d):
    """
    OPTIONAL but recommended.
    TODO: return a mnemonic string (add, lw, beq, jal, etc.)
    Return "NOP" for instr==0 or d is None.
    """
    if d["instr"] == 0 or d == None:
        return "NOP"
    else:
        return "Not NOP"


def trace_cycle(cycle, pc, stall, flush, if_id, id_ex, ex_mem, mem_wb, wb_info):
    """
    TODO: return a ONE-LINE string for this cycle trace.

    Must include at least:
      - cycle number
      - pc (current or next)
      - stall flag
      - flush flag
      - pipeline contents:
          IF/ID, ID/EX, EX/MEM, MEM/WB  (mnemonic recommended)
      - optional: WB action (wb_info)

    Example:
      cycle=5 pc=0x00000014 stall=1 flush=0 | IF/ID=add | ID/EX=lw | EX/MEM=NOP | MEM/WB=addi | WB:x5<-0x0000000C
    """
    return f"Cycle {cycle}\nPC = {pc}\nStall Flag = {stall}\nFlush Flag = {flush}\nIF/ID Reg = {if_id}\nID/EX Reg = {id_ex}\nEX/MEM Reg = {ex_mem}\nMEM/WB Reg = {mem_wb}"


# ------------------------------------------------------------
# Program loader + log writers
# ------------------------------------------------------------

def load_imem_from_file(path):
    """Given."""
    imem = {}
    pc = 0
    f = open(path, "r", encoding="utf-8")
    for line in f:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        if s.lower().startswith("0x"):
            s = s[2:]
        instr = int(s, 16) & MASK32
        imem[pc] = instr
        pc += 4
    f.close()
    return imem


def write_trace_log(lines, path):
    f = open(path, "w", encoding="utf-8")
    for ln in lines:
        f.write(ln + "\n\n")
    f.close()


def write_regs_log(regs, path):
    f = open(path, "w", encoding="utf-8")
    for i in range(32):
        f.write("x%-2d = 0x%08X (%d)\n" % (i, u32(regs[i]), s32(regs[i])))
    f.close()


def write_dmem_log(dmem, path):
    f = open(path, "w", encoding="utf-8")
    for a in sorted(dmem.keys()):
        f.write("0x%08X : 0x%08X (%d)\n" % (u32(a), u32(dmem[a]), s32(dmem[a])))
    f.close()

def write_branch_stats_log(branch_stats, path):
    f = open(path, "w", encoding="utf-8")
    f.write("1-BIT PREDICTOR:\n\n")
    if branch_stats['misses'] != 0:
        f.write(f"Hits: {branch_stats['hits']}\nMisses: {branch_stats['misses']}\nAccuracy: {round(100 * branch_stats['hits'] / (branch_stats['hits'] + branch_stats['misses']), 2)}%\n\nWasted Instructions: {branch_stats['wasted_instructions']}")
    else:
        f.write(f"Hits: {branch_stats['hits']}\nMisses: {branch_stats['misses']}\nAccuracy: Undefined\n\nWasted Instructions: {branch_stats['wasted_instructions']}")
    f.close()


# ------------------------------------------------------------
# Main pipeline simulation loop
# ------------------------------------------------------------

def main():
    imem = load_imem_from_file("hex_inst.txt")

    regs = [0] * 32
    dmem = {}

    pc = 0
    cycle = 0
    max_cycles = 50_000_000

    # Pipeline registers (latched at end of each cycle)
    if_id = make_if_id()
    id_ex = make_id_ex()
    ex_mem = make_ex_mem()
    mem_wb = make_mem_wb()

    # Branch stats
    branch_stats = {}
    branch_stats["hits"] = 0
    branch_stats["misses"] = 0
    branch_stats["wasted_instructions"] = 0

    # Predictor bit
    branch_predict = True

    trace_lines = []
    fetching_done = False

    while cycle < max_cycles:
        # ------------------------------------------------------------
        # WB stage (commit architectural state)
        # ------------------------------------------------------------
        wb_info = ""
        # TODO:
        # If MEM/WB valid and RegWrite:
        #   - choose wb_val:
        #       if MemToReg: mem_data else alu_res
        #       if Jump and RegWrite: wb_val_for_jumps (pc+4)
        #   - if rd != 0: regs[rd] = wb_val
        #   - enforce regs[0] = 0
        #   - set wb_info string like: "WB: x5<-0x0000000C"
        if mem_wb["valid"] == 1 and mem_wb["c"]["RegWrite"] == 1:
            wb_val = None
            if mem_wb["c"]["MemToReg"] == 1:
                wb_val = mem_wb["mem_data"]
            else:
                wb_val = mem_wb["alu_res"]
            if mem_wb["c"]["Jump"] == 1:
                wb_val = mem_wb["wb_val_for_jumps"]
        
            if mem_wb["rd"] != 0:
                regs[mem_wb["rd"]] = wb_val
            
            regs[0] = 0

            if wb_val is not None:
                wb_info = f"WB: x{mem_wb['rd']} <- {hex(wb_val)}"
        

        # ------------------------------------------------------------
        # MEM stage (data memory access)
        # ------------------------------------------------------------
        next_mem_wb = make_mem_wb()
        # TODO:
        # If EX/MEM valid:
        #   - pass c,d,rd,alu_res,pc_plus4,wb_val_for_jumps into MEM/WB
        #   - if MemRead and lw (funct3==010): mem_data = dmem_load_word(dmem, addr)
        #   - if MemWrite and sw (funct3==010): dmem_store_word(dmem, addr, rs2_val_fwd)
        #   - store mem_data into MEM/WB
        if ex_mem["valid"] == 1:
            next_mem_wb["c"] = ex_mem["c"]
            next_mem_wb["d"] = ex_mem["d"]
            next_mem_wb["rd"] = ex_mem["rd"]
            next_mem_wb["alu_res"] = ex_mem["alu_res"]
            next_mem_wb["pc_plus4"] = ex_mem["pc_plus4"]
            next_mem_wb["wb_val_for_jumps"] = ex_mem["wb_val_for_jumps"]
            mem_data = 0

            if ex_mem["c"]["MemRead"] == 1 and ex_mem["d"]["opcode"] == 0x03:
                mem_data = dmem_load_word(dmem, ex_mem["mem_addr"])
            if ex_mem["c"]["MemWrite"] == 1 and ex_mem["d"]["opcode"] == 0x23:
                dmem_store_word(dmem, ex_mem["mem_addr"], ex_mem["rs2_val_fwd"])
            
            next_mem_wb["mem_data"] = mem_data
            next_mem_wb["valid"] = 1

        # ------------------------------------------------------------
        # EX stage (ALU + branch/jump resolution + forwarding)
        # ------------------------------------------------------------
        next_ex_mem = make_ex_mem()
        flush = False
        taken = False
        redirect_pc = 0
        # TODO:
        # If ID/EX valid:
        #   - compute forwarded rs1/rs2 values using forwarding_select(...)
        #   - compute alu_op via id_ex['alu_op'] (precomputed) or call alu_control(c,d)
        #   - select alu_in2 via ALUSrc (imm vs rs2)
        #   - alu_res = alu_exec(...)
        #   - store_data = forwarded rs2 (for sw)
        #
        #   - branch/jump decision resolved in EX:
        #       default next_pc = pc_plus4
        #       if Branch: evaluate branch_taken(BrType, rs1, rs2)
        #           if taken: next_pc = pc + imm_B
        #       if Jump:
        #           taken = True
        #           if JumpReg (jalr): next_pc = (rs1 + imm_I) & ~1
        #           else (jal): next_pc = pc + imm_J
        #
        #   - if taken:
        #       flush = True
        #       redirect_pc = next_pc
        #
        #   - fill EX/MEM bundle with:
        #       c,d,rd,alu_res,mem_addr,rs2_val_fwd,pc_plus4,wb_val_for_jumps
        if id_ex["valid"] == 1:
            if forwarding_select(id_ex["rs1"], ex_mem, mem_wb)[0]:
                id_ex["rs1_val"] = forwarding_select(id_ex["rs1"], ex_mem, mem_wb)[1]
            if forwarding_select(id_ex["rs2"], ex_mem, mem_wb)[0]:
                id_ex["rs2_val"] = forwarding_select(id_ex["rs2"], ex_mem, mem_wb)[1]
            
            if id_ex["c"]["ALUSrc"] == 0:
                alu_in2 = id_ex["rs2_val"]
            else:
                alu_in2 = id_ex["imm"]

            if id_ex["d"]["opcode"] in (0x33, 0x13):
                id_ex["alu_op"] = alu_control(id_ex["c"], id_ex["d"])
            id_ex["alu_res"] = alu_exec(id_ex["alu_op"], id_ex["rs1_val"], alu_in2)
            store_data = id_ex["rs2_val"]

            next_pc = id_ex["pc_plus4"]
            failed_branch = False
            should_branch = (id_ex["c"]["Branch"] == 1 and branch_taken(id_ex["c"]["BrType"], id_ex["rs1_val"], id_ex["rs2_val"]))
            if id_ex["c"]["Branch"] == 1 and (should_branch != branch_predict):
                branch_stats["misses"] += 1
                if should_branch:
                    next_pc = id_ex["pc"] + id_ex["imm"]
                taken = should_branch
                failed_branch = True
                branch_predict = not branch_predict
            elif id_ex["c"]["Jump"] == 1:
                taken = True
                if id_ex["c"]["JumpReg"] != 0:
                    next_pc = (id_ex["rs1_val"] + id_ex["imm"]) & ~1
                else:
                    next_pc = id_ex["pc"] + id_ex["imm"]
            
            if taken or failed_branch:
                flush = True
                redirect_pc = next_pc
            elif id_ex["c"]["Branch"] == 1:
                branch_stats["hits"] += 1

            next_ex_mem["c"] = id_ex["c"]
            next_ex_mem["d"] = id_ex["d"]
            next_ex_mem["rd"] = id_ex["rd"]
            next_ex_mem["alu_res"] = id_ex["alu_res"]
            next_ex_mem["mem_addr"] = id_ex["alu_res"]
            next_ex_mem["rs2_val_fwd"] = id_ex["rs2_val"]
            next_ex_mem["pc_plus4"] = id_ex["pc_plus4"]
            next_ex_mem["wb_val_for_jumps"] = id_ex["pc_plus4"]
            next_ex_mem["valid"] = 1

        # ------------------------------------------------------------
        # ID stage (decode / reg read) + stall insertion
        # ------------------------------------------------------------
        stall = False
        # TODO:
        # stall = load_use_hazard(if_id, id_ex)
        stall = load_use_hazard(if_id, id_ex)

        next_id_ex = make_id_ex()
        # TODO:
        # If not stall and IF/ID valid:
        #   - decode instruction
        #   - control decode
        #   - imm select
        #   - read regs[rs1], regs[rs2]
        #   - compute alu_op and store in ID/EX
        #
        # If flush:
        #   - override next_id_ex to bubble (valid=0)
        #
        # If stall:
        #   - insert bubble into ID/EX (valid=0)
        if not stall and if_id["valid"] == 1:
            next_id_ex["d"] = decode(if_id["instr"])
            next_id_ex["c"] = main_control(next_id_ex["d"])
            next_id_ex["imm"] = select_imm(next_id_ex["d"], next_id_ex["c"])
            next_id_ex["rs1"] = next_id_ex["d"]["rs1"]
            next_id_ex["rs1_val"] = regs[next_id_ex["rs1"]]
            next_id_ex["rs2"] = next_id_ex["d"]["rs2"]
            next_id_ex["rs2_val"] = regs[next_id_ex["rs2"]]
            next_id_ex["rd"] = next_id_ex["d"]["rd"]
            next_id_ex["alu_op"] = next_id_ex["c"]["ALUOp"]
            next_id_ex["valid"] = 1
            next_id_ex["pc"] = if_id["pc"]
            next_id_ex["pc_plus4"] = if_id["pc"] + 4

        if flush:
            if next_id_ex["valid"] == 1:
                branch_stats["wasted_instructions"] += 1
            next_id_ex["valid"] = 0
        
        if stall:
            id_ex["valid"] = 0

        # ------------------------------------------------------------
        # IF stage (fetch) + PC update + stall/flush handling
        # ------------------------------------------------------------
        next_if_id = make_if_id()
        # TODO:
        # If flush:
        #   - set pc = redirect_pc
        #   - set next_if_id to bubble (flush wrong-path)
        # Else if stall:
        #   - freeze IF/ID and PC (next_if_id = if_id; pc unchanged)
        # Else:
        #   - fetch instr from imem[pc]
        #   - if missing -> fetching_done=True; next_if_id.valid=0
        #   - else fill next_if_id fields (pc,instr,valid=1)
        #   - pc = pc + 4
        if flush:
            instr = imem.get(pc)
            if instr != None:
                branch_stats["wasted_instructions"] += 1
            pc = redirect_pc
            next_if_id["valid"] = 0
            fetching_done = False
        elif stall:
            next_if_id = if_id
        else:
            instr = imem.get(pc)
            if instr == None:
                fetching_done = True
                next_if_id["valid"] = 0
            else:
                next_if_id["instr"] = instr
                next_if_id["valid"] = 1
                next_if_id["pc"] = pc
                if get_bits(instr, 6, 0) == 0x63 and branch_predict:
                    pc = pc + imm_b(instr)
                else:
                    pc = pc + 4



        # ------------------------------------------------------------
        # Trace line for this cycle (must be readable)
        # ------------------------------------------------------------
        # TODO:
        # trace_lines.append(trace_cycle(cycle, pc, stall, flush, next_if_id, next_id_ex, next_ex_mem, next_mem_wb, wb_info))
        trace_lines.append(trace_cycle(cycle, pc, stall, flush, next_if_id, next_id_ex, next_ex_mem, next_mem_wb, wb_info))

        # ------------------------------------------------------------
        # Latch pipeline registers (end of cycle)
        # ------------------------------------------------------------
        mem_wb = next_mem_wb
        ex_mem = next_ex_mem
        id_ex = next_id_ex
        if_id = next_if_id

        # ------------------------------------------------------------
        # Halt condition: fetch done + pipeline drained
        # ------------------------------------------------------------
        # TODO:
        # If fetching_done and all pipeline regs invalid:
        #   break
        if fetching_done and if_id["valid"] == 0 and id_ex["valid"] == 0 and ex_mem["valid"] == 0 and mem_wb["valid"] == 0:
            break

        cycle += 1

    # Write logs
    write_trace_log(trace_lines, "trace.log")
    write_regs_log(regs, "regs_final.log")
    write_dmem_log(dmem, "dmem_final.log")
    write_branch_stats_log(branch_stats, "branch_stats.log")

    print("HALT")
    print("cycles =", cycle)
    print("wrote trace.log, regs_final.log, dmem_final.log, branch_stats.log")


if __name__ == "__main__":
    main()
